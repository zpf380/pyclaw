"""CLI commands for pyclaw."""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pyclaw import __version__, __logo__


def _patch_console_encoding() -> None:
    """让控制台以 UTF-8 输出，避免 emoji（如 logo）在 GBK 终端触发 UnicodeEncodeError.

    仅 Windows 下 stdout/stderr 为窄编码时生效；重定向到管道/文件时同样适用。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


# 在任何 rich 输出之前重配编码（否则首次 print logo 即崩溃）
_patch_console_encoding()

app = typer.Typer(
    name="pyclaw",
    help=f"{__logo__} pyclaw - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()

def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} pyclaw v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """pyclaw - Personal AI Assistant."""
    pass

@app.command()
def onboard():
    """Initialize pyclaw configuration and workspace."""
    from pyclaw.config.loader import get_config_path, save_config
    from pyclaw.config.schema import Config
    
    config_path = get_config_path()
    
    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not typer.confirm("Overwrite?"):
            raise typer.Exit()
    
    # Create default config
    config = Config()
    # save_config(config)
    console.print(f"[green]✓[/green] Created config at {config_path}")
    
    # Create workspace
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Created workspace at {workspace}")
    
    # Create default bootstrap files
    _create_workspace_templates(workspace)
    
    console.print(f"\n{__logo__} pyclaw is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]./workspace/pyclaw.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. Chat: [cyan]pyclaw agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/pyclaw#-chat-apps[/dim]")

def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files
""",
        "SOUL.md": """# Soul

I am pyclaw, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }
    
    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")
    
    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
        console.print("  [dim]Created memory/MEMORY.md[/dim]")



@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the pyclaw gateway."""
    from pyclaw.config.loader import load_config, get_data_dir
    from pyclaw.bus.queue import MessageBus

    from pyclaw.cron.service import CronService
    from pyclaw.cron.types import CronJob
    from pyclaw.heartbeat.service import HeartbeatService
    from pyclaw.gateway import GatewayServer
    from pyclaw.providers.litellm_provider import LiteLLMProvider
    from pyclaw.agent.loop import AgentLoop
    from pyclaw.channels.manager import ChannelManager
    console.print(f"{__logo__} Starting pyclaw gateway on port {port}...")
    # 加载配置
    config = load_config()

    # 创建消息组件
    bus = MessageBus()

    # Create provider (supports OpenRouter, Anthropic, OpenAI, Bedrock)
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ./workspace/pyclaw.json under providers.openrouter.apiKey")
        raise typer.Exit(1)
    
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model,
        enable_text_tool_call_fallback=config.get_enable_text_tool_call_fallback(),
    )
    
    # Create cron service first (callback set after agent creation)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    
    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
    )
       
    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from pyclaw.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    cron.on_job = on_cron_job

    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")
    
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True
    )

    # Create channel manager
    channels = ChannelManager(config, bus)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")
    
    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")
    
    console.print(f"[green]✓[/green] Heartbeat: every 30m")

    server = GatewayServer(bus=bus,config=config)
    server.register_agent("AgentLoop", agent)
    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await server.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
            
        except KeyboardInterrupt:
            console.print("\nShutting down...")
            heartbeat.stop()
            server.stop()
            cron.stop()
            agent.stop()  
            await channels.stop_all()
    
    asyncio.run(run())

@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
):
    """Interact with the agent directly."""
    from pyclaw.config.loader import load_config
    from pyclaw.bus.queue import MessageBus
    from pyclaw.providers.litellm_provider import LiteLLMProvider
    from pyclaw.agent.loop import AgentLoop
    
    config = load_config()
    
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        console.print("[red]Error: No API key configured.[/red]")
        raise typer.Exit(1)

    bus = MessageBus()
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model,
        enable_text_tool_call_fallback=config.get_enable_text_tool_call_fallback(),
    )
    
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
    )
    
    if message:
        # Single message mode
        async def run_once():
            response = await agent_loop.process_direct(message, session_id)
            console.print(f"\n{__logo__} {response}")
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        console.print(f"{__logo__} Interactive mode (Ctrl+C to exit)\n")
        
        async def run_interactive():
            while True:
                try:
                    user_input = console.input("[bold blue]You:[/bold blue] ")
                    if not user_input.strip():
                        continue
                    
                    response = await agent_loop.process_direct(user_input, session_id)
                    console.print(f"\n{__logo__} {response}\n")
                except KeyboardInterrupt:
                    console.print("\nGoodbye!")
                    break
        
        asyncio.run(run_interactive())

@app.command()
def status():
    """显示 pyclaw 运行状态（配置路径/模型/渠道/定时任务）."""
    from pyclaw.config.loader import load_config, get_config_path, get_data_dir
    from pyclaw.bus.queue import MessageBus
    from pyclaw.channels.manager import ChannelManager
    from pyclaw.cron.service import CronService

    config = load_config()
    channels = ChannelManager(config, MessageBus())
    cron = CronService(get_data_dir() / "cron" / "jobs.json")
    cron_status = cron.status()

    table = Table(title="pyclaw 状态")
    table.add_column("项目")
    table.add_column("值")

    table.add_row("版本", f"v{__version__}")
    table.add_row("配置路径", str(get_config_path()))
    table.add_row("模型", config.agents.defaults.model)
    table.add_row(
        "启用渠道",
        ", ".join(channels.enabled_channels) if channels.enabled_channels else "(无)",
    )
    table.add_row("定时任务", str(cron_status["jobs"]))
    table.add_row("定时服务", "运行中" if cron_status["enabled"] else "未运行")

    console.print(table)

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")

@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """列出定时任务."""
    from pyclaw.config.loader import get_data_dir
    from pyclaw.cron.service import CronService

    cron = CronService(get_data_dir() / "cron" / "jobs.json")
    jobs = cron.list_jobs(include_disabled=all)

    if not jobs:
        console.print("[yellow]没有定时任务[/yellow]")
        return

    table = Table(title="定时任务")
    table.add_column("ID")
    table.add_column("名称")
    table.add_column("调度")
    table.add_column("内容")
    table.add_column("状态")

    for job in jobs:
        sched = job.schedule
        if sched.kind == "cron":
            schedule_str = f"cron: {sched.expr}"
        elif sched.kind == "every":
            schedule_str = f"每 {sched.every_ms / 1000:.0f}s"
        elif sched.kind == "at":
            schedule_str = f"at: {sched.at_ms}"
        else:
            schedule_str = str(sched.kind)
        table.add_row(
            job.id,
            job.name,
            schedule_str,
            job.payload.message,
            "启用" if job.enabled else "停用",
        )

    console.print(table)

channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")

@channels_app.command("status")
def channels_status():
    """显示渠道运行状态."""
    from pyclaw.config.loader import load_config
    from pyclaw.bus.queue import MessageBus
    from pyclaw.channels.manager import ChannelManager

    config = load_config()
    channels = ChannelManager(config, MessageBus())
    status = channels.get_status()

    if not status:
        console.print("[yellow]没有启用的渠道[/yellow]")
        return

    table = Table(title="渠道状态")
    table.add_column("渠道")
    table.add_column("运行状态")

    for name, info in status.items():
        table.add_row(name, "运行中" if info["running"] else "已停止")

    console.print(table)

skills_app = typer.Typer(help="Manage skills")
app.add_typer(skills_app, name="skills")

@skills_app.command("list")
def skills_list():
    """列出技能（与 system.listSkills 同源，读 DB）. """
    from pyclaw.database.database import DatabaseManager

    db = DatabaseManager()
    skills = db.get_all_skills()

    if not skills:
        console.print("[yellow]没有技能[/yellow]")
        return

    table = Table(title="技能列表")
    table.add_column("名称")
    table.add_column("编码")
    table.add_column("类别")
    table.add_column("描述")
    table.add_column("状态")

    for s in skills:
        table.add_row(
            s.get("name", ""),
            s.get("code", ""),
            s.get("category", ""),
            s.get("description", ""),
            "启用" if s.get("status") == "active" else "停用",
        )

    console.print(table)

if __name__ == "__main__":
    app()
