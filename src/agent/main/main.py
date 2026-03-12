"""
A2W Lucas Interactive Agent

A Slack-integrated Claude agent that:
1. Responds to @mentions for on-demand tasks
2. Runs scheduled scans and can ask clarifying questions
3. Maintains conversation context across thread replies
"""

import asyncio
import logging
import os
import re
from pathlib import Path

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

try:
    from .cluster_snapshot import build_interactive_snapshot, build_namespace_snapshot
    from .llm import calculate_cost, create_backend, resolve_llm_config, validate_llm_config
    from .report_utils import extract_report_payload, format_slack_scan_message, parse_run_report
    from .slack_actions import (
        confirmation_accepted,
        confirmation_prompt,
        execute_slack_kube_action,
        format_action_audit_line,
        parse_slack_kube_action,
        slack_action_allowed,
    )
    from .sessions import SessionStore, RunStore
    from .tools import SlackTools, resolve_pending_reply
    from .scheduler import SREScheduler
except ImportError:
    from cluster_snapshot import build_interactive_snapshot, build_namespace_snapshot
    from llm import calculate_cost, create_backend, resolve_llm_config, validate_llm_config
    from report_utils import extract_report_payload, format_slack_scan_message, parse_run_report
    from slack_actions import (
        confirmation_accepted,
        confirmation_prompt,
        execute_slack_kube_action,
        format_action_audit_line,
        parse_slack_kube_action,
        slack_action_allowed,
    )
    from sessions import SessionStore, RunStore
    from tools import SlackTools, resolve_pending_reply
    from scheduler import SREScheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
slack_bot_user_id = os.environ.get("SLACK_BOT_USER_ID", "")
SRE_ALERT_CHANNEL = os.environ.get("SRE_ALERT_CHANNEL", "")
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))

# SRE_MODE: "autonomous" (can make changes) or "watcher" (read-only, report only)
SRE_MODE = os.environ.get("SRE_MODE", "autonomous")
PROMPT_FILE = os.environ.get(
    "PROMPT_FILE",
    "/app/master-prompt-interactive-report.md" if SRE_MODE == "watcher" else "/app/master-prompt-interactive.md",
)

LLM_CONFIG = resolve_llm_config()
llm_backend = create_backend(LLM_CONFIG)


# Initialize Slack app
app = AsyncApp(token=SLACK_BOT_TOKEN)

# Global instances (initialized in main)
session_store: SessionStore | None = None
run_store: RunStore | None = None
slack_tools: SlackTools | None = None
scheduler: SREScheduler | None = None
slack_client: AsyncWebClient | None = None


def load_system_prompt(namespace: str | None = None, thread_ts: str | None = None, channel: str | None = None) -> str:
    """Load and customize the system prompt."""
    try:
        prompt = Path(PROMPT_FILE).read_text()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {PROMPT_FILE}")
        prompt = "You are Lucas, an agent. Help monitor and fix Kubernetes issues."

    # Replace placeholders
    replacements = {
        "$TARGET_NAMESPACE": namespace or os.environ.get("TARGET_NAMESPACE", "default"),
        "$SLACK_CHANNEL": channel or SRE_ALERT_CHANNEL,
        "$SLACK_THREAD_TS": thread_ts or "",
    }
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    return prompt


def default_model_name() -> str:
    return LLM_CONFIG.model or "unknown"


def sanitize_slack_text(text: str) -> str:
    return re.sub(r'<@[A-Z0-9]+>', '', text or '').strip()


async def build_thread_history(channel: str, thread_ts: str, exclude_ts: str | None = None) -> list[dict[str, str]]:
    if not slack_client:
        return []

    history: list[dict[str, str]] = []
    replies = await slack_client.conversations_replies(channel=channel, ts=thread_ts, limit=20)
    for message in replies.get("messages", []):
        if exclude_ts and message.get("ts") == exclude_ts:
            continue
        text = sanitize_slack_text(message.get("text", ""))
        if not text:
            continue
        role = "assistant" if message.get("user") == slack_bot_user_id or message.get("bot_id") else "user"
        history.append({"role": role, "content": text})
    return history[-12:]


async def build_dm_history(channel: str, exclude_ts: str | None = None) -> list[dict[str, str]]:
    if not slack_client:
        return []

    history: list[dict[str, str]] = []
    response = await slack_client.conversations_history(channel=channel, limit=15)
    messages = list(reversed(response.get("messages", [])))
    for message in messages:
        if exclude_ts and message.get("ts") == exclude_ts:
            continue
        text = sanitize_slack_text(message.get("text", ""))
        if not text:
            continue
        role = "assistant" if message.get("user") == slack_bot_user_id or message.get("bot_id") else "user"
        history.append({"role": role, "content": text})
    return history[-12:]


async def run_agent(
    prompt: str,
    session_id: str | None = None,
    namespace: str | None = None,
    thread_ts: str | None = None,
    channel: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, str | None, dict[str, int | float | str]]:
    system_prompt = load_system_prompt(namespace, thread_ts, channel)
    effective_prompt = prompt

    if LLM_CONFIG.backend == "openai-compatible":
        snapshot_namespace = namespace or os.environ.get("TARGET_NAMESPACE", "default")
        snapshot = build_interactive_snapshot(prompt, snapshot_namespace)
        effective_prompt = (
            prompt
            + "\n\nUse ONLY the Kubernetes data below as ground truth. "
            + "Do not output commands to run. Do not mention bash, kubectl, sqlite3, or tool transcripts. "
            + "Answer directly with the result itself in concise Slack-friendly text. "
            + "If asked for a list, print the list directly. If data is missing, say what is missing. "
            + "Respond primarily in Korean unless the user clearly asks for another language.\n\n"
            + snapshot
        )

    logger.info(
        "Running backend=%s provider=%s session=%s namespace=%s",
        LLM_CONFIG.backend,
        LLM_CONFIG.provider,
        session_id,
        namespace,
    )

    result = await llm_backend.run(
        prompt=effective_prompt,
        system_prompt=system_prompt,
        session_id=session_id if LLM_CONFIG.supports_resume else None,
        context={
            "namespace": namespace,
            "thread_ts": thread_ts,
            "channel": channel,
            "history": history or [],
        },
    )

    token_usage = {
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "model": result.get("model", default_model_name()),
        "cost": result.get("cost", 0.0),
    }
    return result.get("text", "No response from agent"), result.get("session_id"), token_usage


async def handle_slack_ask_in_prompt(
    response_text: str,
    channel: str,
    thread_ts: str
) -> tuple[str, bool]:
    """
    Check if Claude's response contains a slack_ask request and handle it.

    This is a workaround for custom tools - we detect special markers in the response.

    Returns:
        Tuple of (final_response, had_interaction)
    """
    # Look for slack_ask pattern in response
    # Claude might output something like: [SLACK_ASK: question here]
    ask_pattern = r'\[SLACK_ASK:\s*(.+?)\]'
    match = re.search(ask_pattern, response_text, re.DOTALL)

    if match:
        question = match.group(1).strip()
        logger.info(f"Detected slack_ask request: {question[:100]}...")

        # Ask via Slack and wait for reply
        reply = await slack_tools.slack_ask(
            message=question,
            channel=channel,
            thread_ts=thread_ts,
            timeout=300
        )

        # Return the reply for Claude to continue
        return reply, True

    return response_text, False


async def maybe_handle_slack_action(
    *,
    text: str,
    channel: str,
    thread_ts: str,
    user_id: str,
    say,
) -> bool:
    default_namespace = os.environ.get("TARGET_NAMESPACE", "default")
    parsed = parse_slack_kube_action(text, default_namespace)
    if not parsed.matched:
        return False

    action = parsed.action
    action_namespace = action.namespace if action is not None else default_namespace
    allowed, denial_reason = slack_action_allowed(channel, user_id, action_namespace)
    if not allowed:
        await say(text=denial_reason or "이 작업은 허용되지 않습니다.", thread_ts=thread_ts)
        return True

    if parsed.error:
        await say(text=parsed.error, thread_ts=thread_ts)
        return True

    if action is None:
        await say(text="지원되는 명령을 해석하지 못했습니다.", thread_ts=thread_ts)
        return True

    logger.info("Slack emergency action requested by %s in %s: %s", user_id, channel, format_action_audit_line(action))

    if action.is_mutating:
        confirmation = await slack_tools.slack_ask(
            message=confirmation_prompt(action),
            channel=channel,
            thread_ts=thread_ts,
            timeout=180,
        )
        if not confirmation_accepted(confirmation):
            await say(text="작업이 취소되었습니다.", thread_ts=thread_ts)
            logger.info("Slack emergency action cancelled: %s", format_action_audit_line(action))
            return True

    try:
        result = execute_slack_kube_action(action)
        await say(text=result[:3900], thread_ts=thread_ts)
        logger.info("Slack emergency action executed: %s", format_action_audit_line(action))
    except Exception as exc:
        logger.error("Slack emergency action failed: %s", exc, exc_info=True)
        await say(text=f":x: 작업 실행 실패: {str(exc)}"[:3900], thread_ts=thread_ts)
    return True


# ============================================================
# SLACK EVENT HANDLERS
# ============================================================

@app.event("app_mention")
async def handle_mention(event: dict[str, object], say):
    """Handle @mentions of the bot."""
    channel = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    user_message = event.get("text", "")
    user_id = event.get("user", "")

    # Remove the bot mention from the message
    user_message = sanitize_slack_text(user_message)

    if not user_message:
        await say(
            text="Hi! I'm Lucas. Ask me to check pods, investigate issues, or help with Kubernetes tasks.",
            thread_ts=thread_ts
        )
        return

    if await maybe_handle_slack_action(
        text=user_message,
        channel=channel,
        thread_ts=thread_ts,
        user_id=str(user_id),
        say=say,
    ):
        return

    logger.info(f"Mention from {user_id} in {channel}: {user_message[:100]}...")

    # Check for existing session
    session_id = await session_store.get_session(thread_ts)

    # Send typing indicator
    await say(text=":robot_face: Investigating...", thread_ts=thread_ts)

    try:
        response, new_session_id, token_usage = await run_agent(
            prompt=user_message,
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts
        )

        # Save session mapping
        if new_session_id:
            await session_store.save_session(thread_ts, new_session_id, channel)

        # Check for slack_ask requests and handle them
        while True:
            reply, had_interaction = await handle_slack_ask_in_prompt(
                response, channel, thread_ts
            )
            if not had_interaction:
                break

            # Continue the conversation with the user's reply
            response, new_session_id, more_tokens = await run_agent(
                prompt=f"User replied: {reply}",
                session_id=new_session_id,
                channel=channel,
                thread_ts=thread_ts
            )
            # Accumulate token usage
            token_usage["input_tokens"] += more_tokens.get("input_tokens", 0)
            token_usage["output_tokens"] += more_tokens.get("output_tokens", 0)
            token_usage["cost"] = token_usage.get("cost", 0) + more_tokens.get("cost", 0)

        # Record token usage for interactive messages (without run_id)
        if token_usage.get("input_tokens") or token_usage.get("output_tokens"):
            try:
                await run_store.record_token_usage(
                    run_id=0,  # No run_id for interactive messages
                    namespace="interactive",
                    model=token_usage.get("model", default_model_name()),
                    input_tokens=token_usage.get("input_tokens", 0),
                    output_tokens=token_usage.get("output_tokens", 0),
                    cost=token_usage.get("cost", 0)
                )
            except Exception as e:
                logger.warning(f"Failed to record token usage: {e}")

        # Send final response
        # Truncate if too long for Slack
        if len(response) > 3900:
            response = response[:3900] + "\n\n_(Response truncated)_"

        await say(text=response, thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"Error handling mention: {e}", exc_info=True)
        await say(
            text=f":x: Error: {str(e)}",
            thread_ts=thread_ts
        )


@app.event("message")
async def handle_message(event: dict[str, object], say):
    """Handle messages - thread replies and direct messages."""
    # Ignore bot messages
    if event.get("bot_id") or event.get("subtype"):
        return

    thread_ts = event.get("thread_ts")
    channel = event["channel"]
    text = event.get("text", "")
    channel_type = event.get("channel_type", "")

    # Check if this is a reply to a pending slack_ask
    if thread_ts and resolve_pending_reply(thread_ts, text):
        logger.info(f"Resolved pending reply for thread {thread_ts}")
        return

    # Handle direct messages (DMs)
    if channel_type == "im":
        logger.info(f"DM received: {text[:100]}...")

        if await maybe_handle_slack_action(
            text=text,
            channel=channel,
            thread_ts=event.get("ts", channel),
            user_id=str(event.get("user", "")),
            say=say,
        ):
            return

        # Use channel as thread_ts for DM session tracking
        dm_session_key = f"dm_{channel}"
        session_id = await session_store.get_session(dm_session_key)

        try:
            history = None if LLM_CONFIG.supports_resume else await build_dm_history(channel, exclude_ts=event.get("ts"))
            response, new_session_id, token_usage = await run_agent(
                prompt=text,
                session_id=session_id,
                channel=channel,
                history=history,
            )

            # Save session for DM continuity
            if new_session_id:
                await session_store.save_session(dm_session_key, new_session_id, channel)

            # Record token usage for DMs
            if token_usage.get("input_tokens") or token_usage.get("output_tokens"):
                try:
                    await run_store.record_token_usage(
                        run_id=0,
                        namespace="dm",
                        model=token_usage.get("model", default_model_name()),
                        input_tokens=token_usage.get("input_tokens", 0),
                        output_tokens=token_usage.get("output_tokens", 0),
                        cost=token_usage.get("cost", 0)
                    )
                except Exception as e:
                    logger.warning(f"Failed to record token usage: {e}")

            if len(response) > 3900:
                response = response[:3900] + "\n\n_(Response truncated)_"

            await say(text=response)

        except Exception as e:
            logger.error(f"Error handling DM: {e}", exc_info=True)
            await say(text=f"Error: {str(e)}")
        return

    # Handle thread replies in channels
    if not thread_ts:
        # Not a thread reply and not a DM, ignore (mentions are handled separately)
        return

    # Check if this thread has an active session
    session_id = await session_store.get_session(thread_ts)
    if not session_id and LLM_CONFIG.supports_resume:
        # No session for this thread, ignore
        return

    logger.info(f"Thread reply in session {session_id}: {text[:100]}...")

    if await maybe_handle_slack_action(
        text=text,
        channel=channel,
        thread_ts=thread_ts,
        user_id=str(event.get("user", "")),
        say=say,
    ):
        return

    try:
        # Continue the conversation
        history = None if LLM_CONFIG.supports_resume else await build_thread_history(channel, thread_ts, exclude_ts=event.get("ts"))
        if history is not None and not any(message.get("role") == "assistant" for message in history):
            return
        response, new_session_id, token_usage = await run_agent(
            prompt=text,
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts,
            history=history,
        )

        # Update session if changed
        if new_session_id and new_session_id != session_id:
            await session_store.save_session(thread_ts, new_session_id, channel)

        # Record token usage for thread replies
        if token_usage.get("input_tokens") or token_usage.get("output_tokens"):
            try:
                await run_store.record_token_usage(
                    run_id=0,
                    namespace="thread",
                    model=token_usage.get("model", default_model_name()),
                    input_tokens=token_usage.get("input_tokens", 0),
                    output_tokens=token_usage.get("output_tokens", 0),
                    cost=token_usage.get("cost", 0)
                )
            except Exception as e:
                logger.warning(f"Failed to record token usage: {e}")

        # Truncate if needed
        if len(response) > 3900:
            response = response[:3900] + "\n\n_(Response truncated)_"

        await say(text=response, thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"Error handling thread reply: {e}", exc_info=True)
        await say(text=f"Error: {str(e)}", thread_ts=thread_ts)


# ============================================================
# SCHEDULED SCAN CALLBACK
# ============================================================

async def run_scheduled_scan(namespace: str):
    """
    Run a scheduled scan for a namespace.

    This is called by the scheduler and can result in alerts being posted to Slack.
    """
    if not SRE_ALERT_CHANNEL:
        logger.warning("SRE_ALERT_CHANNEL not set, skipping scheduled scan")
        return

    logger.info(f"Running scheduled scan for namespace: {namespace}")

    # Create run record in database
    run_id = await run_store.create_run(namespace, mode=SRE_MODE)
    logger.info(f"Created run #{run_id} for namespace {namespace}")

    prompt = f"""Run a health check on namespace '{namespace}'.

Check for:
1. Pods in error states (CrashLoopBackOff, Error, ImagePullBackOff)
2. Pods with high restart counts
3. Recent errors in pod logs

If you find issues that need human attention or decision, use [SLACK_ASK: your question here] to ask.
If everything is healthy, just confirm briefly.
If you find critical issues, report them clearly.

At the end, provide a brief summary with counts: how many pods checked, how many had errors.
"""

    if LLM_CONFIG.backend == "openai-compatible":
        snapshot = build_namespace_snapshot(namespace)
        prompt = (
            prompt
            + "\n\nUse the following Kubernetes snapshot as ground truth for your analysis. "
            + "Do not claim you ran tools that are not available in this backend. "
            + "Do not include shell transcripts, command echoes, or code fences in the final answer. "
            + "Give a concise result-oriented summary only. "
            + "Write the summary and recommendations in Korean.\n\n"
            + snapshot
        )

    try:
        response, session_id, token_usage = await run_agent(
            prompt=prompt,
            namespace=namespace,
            channel=SRE_ALERT_CHANNEL
        )

        # Record token usage for this run
        if token_usage.get("input_tokens") or token_usage.get("output_tokens"):
            # Use cost from Claude CLI if available, otherwise calculate
            cost = token_usage.get("cost", 0.0)
            if not cost and LLM_CONFIG.backend == "claude-code":
                cost = calculate_cost(
                    token_usage.get("model", default_model_name()),
                    token_usage.get("input_tokens", 0),
                    token_usage.get("output_tokens", 0)
                )
            await run_store.record_token_usage(
                run_id=run_id,
                namespace=namespace,
                model=token_usage.get("model", default_model_name()),
                input_tokens=token_usage.get("input_tokens", 0),
                output_tokens=token_usage.get("output_tokens", 0),
                cost=cost
            )
            logger.info(f"Recorded token usage: {token_usage.get('input_tokens', 0)} in, {token_usage.get('output_tokens', 0)} out, ${cost:.4f}")

        report_text, _ = extract_report_payload(response)
        parsed_report = parse_run_report(report_text)
        pod_count = int(parsed_report["pod_count"])
        error_count = int(parsed_report["error_count"])
        status = str(parsed_report["status"])
        details = parsed_report["details"] if isinstance(parsed_report["details"], list) else []
        summary = str(parsed_report["summary"])

        # Update run record
        await run_store.update_run(
            run_id=run_id,
            status=status,
            pod_count=pod_count,
            error_count=error_count,
            fix_count=0,
            report=report_text[:5000] if report_text else None,
            log=response[:10000] if response else None
        )

        if status == "issues_found":
            # Post alert to Slack
            slack_client = AsyncWebClient(token=SLACK_BOT_TOKEN)
            result = await slack_client.chat_postMessage(
                channel=SRE_ALERT_CHANNEL,
                text=format_slack_scan_message(
                    status=status,
                    namespace=namespace,
                    run_id=run_id,
                    summary=summary,
                    pod_count=pod_count,
                    error_count=error_count,
                    details=details,
                ) + "\n\n_Reply to this thread for follow-up_"
            )

            # Save session for potential follow-up
            if session_id:
                await session_store.save_session(
                    result["ts"],
                    session_id,
                    SRE_ALERT_CHANNEL,
                    namespace
                )

            logger.info(f"Posted alert for {namespace}, thread_ts={result['ts']}")
        else:
            logger.info(f"Scan of {namespace} completed, no issues found")

    except Exception as e:
        logger.error(f"Error in scheduled scan for {namespace}: {e}", exc_info=True)
        # Update run as failed
        await run_store.update_run(
            run_id=run_id,
            status="failed",
            report=str(e)
        )


# ============================================================
# MAIN
# ============================================================

async def main():
    """Main entry point."""
    global session_store, run_store, slack_tools, scheduler

    logger.info("Starting A2W Lucas Interactive Agent...")
    validate_llm_config(LLM_CONFIG)
    logger.info("Backend=%s provider=%s model=%s", LLM_CONFIG.backend, LLM_CONFIG.provider, LLM_CONFIG.model)
    logger.info("Resume support=%s", LLM_CONFIG.supports_resume)
    if LLM_CONFIG.backend == "claude-code":
        logger.info("Skills-based runbook system enabled (auto-loaded by Claude Code)")

    # Validate required environment variables
    if not SLACK_BOT_TOKEN:
        raise ValueError("SLACK_BOT_TOKEN is required")
    if not SLACK_APP_TOKEN:
        raise ValueError("SLACK_APP_TOKEN is required")

    # Initialize session store
    session_store = SessionStore()
    await session_store.connect()
    logger.info("Session store initialized")

    # Initialize run store (for dashboard)
    run_store = RunStore()
    await run_store.connect()
    logger.info("Run store initialized")

    # Initialize Slack tools
    global slack_client
    slack_client = AsyncWebClient(token=SLACK_BOT_TOKEN)
    slack_tools = SlackTools(slack_client, default_channel=SRE_ALERT_CHANNEL)

    # Get bot user ID if not set
    global slack_bot_user_id
    if not slack_bot_user_id:
        auth_response = await slack_client.auth_test()
        slack_bot_user_id = auth_response["user_id"]
        logger.info(f"Bot user ID: {slack_bot_user_id}")

    # Initialize scheduler for periodic scans
    scheduler = SREScheduler(
        scan_callback=run_scheduled_scan,
        interval_seconds=SCAN_INTERVAL
    )

    # Start scheduler if alert channel is configured
    if SRE_ALERT_CHANNEL:
        await scheduler.start()
        logger.info("Scheduler started")
    else:
        logger.warning("SRE_ALERT_CHANNEL not set, scheduled scans disabled")

    # Start session cleanup task (runs daily, cleans sessions older than 7 days)
    async def cleanup_loop():
        while True:
            await asyncio.sleep(86400)  # Run once per day
            try:
                deleted = await session_store.cleanup_old_sessions(days=7)
                count = await session_store.get_session_count()
                logger.info(f"Session cleanup: deleted {deleted}, remaining {count}")
            except Exception as e:
                logger.error(f"Session cleanup failed: {e}")

    _ = asyncio.create_task(cleanup_loop())
    logger.info("Session cleanup task started (daily, 7-day retention)")

    # Start Slack handler
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)

    logger.info("Lucas Agent ready! Listening for Slack events...")

    try:
        await handler.start_async()
    finally:
        await scheduler.stop()
        await session_store.close()
        await run_store.close()


if __name__ == "__main__":
    asyncio.run(main())
