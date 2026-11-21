
import os
import sqlite3
import traceback
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

# =========================================================
# 환경 설정 - TOKEN 직접 입력 방식
# =========================================================

access_token = os.environ ["TOKEN"]
TOKEN = "access_token"

GUILD_ID = 123456789012345678
LOG_CHANNEL_ID = 123456789012345678

if not TOKEN or TOKEN == "여기에_디스코드_봇_토큰_입력":
    raise RuntimeError("봇 토큰을 입력해주세요.")

if GUILD_ID <= 0:
    raise RuntimeError("올바른 서버 ID를 입력해주세요.")

GUILD_OBJECT = discord.Object(id=GUILD_ID)

DB_PATH = "warnings.db"

COLOR_BLUE = 0x5865F2
COLOR_GREEN = 0x2ECC71
COLOR_RED = 0xE74C3C
COLOR_ORANGE = 0xF39C12
COLOR_PURPLE = 0x9B59B6
COLOR_CYAN = 0x1ABC9C


# =========================================================
# 데이터베이스
# =========================================================

db = sqlite3.connect(DB_PATH)

db.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")

db.commit()


# =========================================================
# 봇 및 공통 UI
# =========================================================

intents = discord.Intents.default()
intents.members = True


class ModerationBot(commands.Bot):
    async def setup_hook(self):
        try:
            synced = await self.tree.sync(guild=GUILD_OBJECT)
            print(f"[완료] 서버 전용 슬래시 명령어 {len(synced)}개 등록")
        except discord.HTTPException as exc:
            print(f"[명령어 등록 실패] HTTP {exc.status}: {exc}")
            raise


bot = ModerationBot(command_prefix="!", intents=intents)


def make_embed(title: str, description: str, color: int = COLOR_BLUE):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="서버 관리 시스템 • Moderation")
    return embed


async def send_log(guild: discord.Guild | None, embed: discord.Embed):
    if guild is None or LOG_CHANNEL_ID <= 0:
        return

    try:
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            channel = await guild.fetch_channel(LOG_CHANNEL_ID)

        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed)

    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"[로그 전송 실패] {type(exc).__name__}: {exc}")


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    embed: discord.Embed | None = None,
    *,
    ephemeral: bool = True,
):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral
            )
        else:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                ephemeral=ephemeral
            )

    except discord.HTTPException as exc:
        print(f"[응답 전송 실패] {exc}")


async def complete(
    interaction: discord.Interaction,
    title: str,
    description: str,
    color: int = COLOR_GREEN,
):
    embed = make_embed(title, description, color)
    await respond(interaction, embed=embed, ephemeral=True)
    await send_log(interaction.guild, embed)


async def start_command(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        await respond(interaction, "이 명령어는 서버 안에서만 사용할 수 있습니다.")
        return False

    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        return True

    except discord.HTTPException as exc:
        print(f"[defer 실패] {exc}")
        return False


async def notify_user(user: discord.abc.User, message: str):
    try:
        await user.send(message)
        return True

    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"[DM 전송 생략] {type(exc).__name__}: {exc}")
        return False


async def get_bot_member(guild: discord.Guild):
    if bot.user is None:
        return None

    member = guild.get_member(bot.user.id)

    if member is None:
        try:
            member = await guild.fetch_member(bot.user.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    return member


def check_hierarchy(
    interaction: discord.Interaction,
    target: discord.Member,
):
    guild = interaction.guild
    moderator = interaction.user

    if guild is None or not isinstance(moderator, discord.Member):
        return "서버 정보를 확인할 수 없습니다."

    if target.id == moderator.id:
        return "자기 자신에게는 이 처벌을 사용할 수 없습니다."

    if target.id == guild.owner_id:
        return "서버 소유자에게는 이 처벌을 사용할 수 없습니다."

    if bot.user and target.id == bot.user.id:
        return "봇 자신에게는 이 처벌을 사용할 수 없습니다."

    if moderator.id != guild.owner_id and moderator.top_role <= target.top_role:
        return "대상자의 역할이 본인과 같거나 높아 처벌할 수 없습니다."

    bot_member = guild.me

    if bot_member is None:
        return "봇의 서버 멤버 정보를 확인할 수 없습니다."

    if bot_member.top_role <= target.top_role:
        return "봇 역할을 대상자 역할보다 위로 올려주세요."

    return None


async def check_bot_permission(
    interaction: discord.Interaction,
    permission: str
):
    guild = interaction.guild

    if guild is None:
        await respond(interaction, "서버 안에서만 사용할 수 있습니다.")
        return False

    bot_member = await get_bot_member(guild)

    if bot_member is None:
        await respond(interaction, "봇의 서버 권한 정보를 가져오지 못했습니다.")
        return False

    if not getattr(bot_member.guild_permissions, permission, False):
        await respond(
            interaction,
            f"봇에게 `{permission}` 권한이 없습니다."
        )
        return False

    return True


# =========================================================
# 온라인 / 오류 처리
# =========================================================

@bot.event
async def on_ready():
    print("=" * 55)
    print(f"[온라인] {bot.user} ({bot.user.id})")
    print(f"[서버 ID] {GUILD_ID}")
    print("[상태] 관리 봇 실행 중")
    print("=" * 55)


@bot.tree.error
async def on_app_command_error(interaction, error):
    original = getattr(error, "original", error)

    print("\n[슬래시 명령어 오류]")
    traceback.print_exception(type(original), original, original.__traceback__)

    if isinstance(error, app_commands.MissingPermissions):
        message = "명령어를 실행할 본인 권한이 부족합니다."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "봇 권한이 부족합니다."
    elif isinstance(original, discord.Forbidden):
        message = "Discord가 작업을 거부했습니다. 봇 권한과 역할 순서를 확인하세요."
    elif isinstance(original, discord.NotFound):
        message = "대상 또는 요청한 항목을 찾을 수 없습니다."
    elif isinstance(original, discord.HTTPException):
        message = f"Discord API 오류 코드: {original.code}"
    else:
        message = "처리 중 예기치 않은 오류가 발생했습니다."

    await respond(interaction, f"⚠️ {message}")


# =========================================================
# 1. 추방
# =========================================================

@bot.tree.command(name="추방", description="멤버를 서버에서 추방합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(kick_members=True)
@app_commands.checks.has_permissions(kick_members=True)
async def 추방(interaction: discord.Interaction, 대상: discord.Member, 사유: str = "사유 없음"):
    if not await start_command(interaction):
        return

    issue = check_hierarchy(interaction, 대상)
    if issue:
        return await respond(interaction, issue)

    if not await check_bot_permission(interaction, "kick_members"):
        return

    try:
        await notify_user(대상, f"{interaction.guild.name} 서버에서 추방되었습니다.\n사유: {사유}")
        await 대상.kick(reason=f"{사유} | 담당자: {interaction.user}")
        await complete(interaction, "👢 멤버 추방 완료", f"대상: {대상}\n사유: {사유}", COLOR_RED)

    except discord.Forbidden:
        await respond(interaction, "추방 실패: 봇 권한과 역할 순서를 확인하세요.")


# =========================================================
# 2. 차단
# =========================================================

@bot.tree.command(name="차단", description="멤버를 서버에서 차단합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
async def 차단(
    interaction: discord.Interaction,
    대상: discord.Member,
    사유: str = "사유 없음",
    메시지삭제일수: app_commands.Range[int, 0, 7] = 0
):
    if not await start_command(interaction):
        return

    issue = check_hierarchy(interaction, 대상)
    if issue:
        return await respond(interaction, issue)

    if not await check_bot_permission(interaction, "ban_members"):
        return

    try:
        await notify_user(대상, f"{interaction.guild.name} 서버에서 차단되었습니다.\n사유: {사유}")

        await 대상.ban(
            reason=f"{사유} | 담당자: {interaction.user}",
            delete_message_seconds=메시지삭제일수 * 86400
        )

        await complete(
            interaction,
            "🔨 멤버 차단 완료",
            f"대상: {대상}\n사유: {사유}\n메시지 삭제: {메시지삭제일수}일",
            COLOR_RED
        )

    except discord.Forbidden:
        await respond(interaction, "차단 실패: 봇 권한과 역할 순서를 확인하세요.")


# =========================================================
# 3. 차단 해제
# =========================================================

@bot.tree.command(name="차단해제", description="유저 ID로 서버 차단을 해제합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
async def 차단해제(interaction: discord.Interaction, 유저아이디: str, 사유: str = "사유 없음"):
    if not await start_command(interaction):
        return

    if not 유저아이디.isdigit():
        return await respond(interaction, "유저 ID는 숫자만 입력해야 합니다.")

    try:
        user = await bot.fetch_user(int(유저아이디))
        await interaction.guild.unban(user, reason=사유)

        await complete(interaction, "🔓 차단 해제 완료", f"대상: {user}\n사유: {사유}")

    except discord.NotFound:
        await respond(interaction, "해당 사용자는 차단 상태가 아닙니다.")


# =========================================================
# 4. 타임아웃
# =========================================================

@bot.tree.command(name="타임아웃", description="멤버에게 타임아웃을 적용합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def 타임아웃(
    interaction: discord.Interaction,
    대상: discord.Member,
    분: app_commands.Range[int, 1, 40320],
    사유: str = "사유 없음"
):
    if not await start_command(interaction):
        return

    issue = check_hierarchy(interaction, 대상)
    if issue:
        return await respond(interaction, issue)

    if not await check_bot_permission(interaction, "moderate_members"):
        return

    try:
        await notify_user(대상, f"{interaction.guild.name} 서버에서 타임아웃되었습니다.\n시간: {분}분\n사유: {사유}")
        await 대상.timeout(timedelta(minutes=분), reason=사유)

        await complete(interaction, "⏳ 타임아웃 적용 완료", f"대상: {대상.mention}\n시간: {분}분\n사유: {사유}", COLOR_ORANGE)

    except discord.Forbidden:
        await respond(interaction, "타임아웃 실패: 권한과 역할 순서를 확인하세요.")


# =========================================================
# 5. 타임아웃 해제
# =========================================================

@bot.tree.command(name="타임아웃해제", description="멤버의 타임아웃을 해제합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def 타임아웃해제(interaction: discord.Interaction, 대상: discord.Member, 사유: str = "사유 없음"):
    if not await start_command(interaction):
        return

    issue = check_hierarchy(interaction, 대상)
    if issue:
        return await respond(interaction, issue)

    try:
        await 대상.timeout(None, reason=사유)
        await complete(interaction, "✅ 타임아웃 해제 완료", f"대상: {대상.mention}\n사유: {사유}")

    except discord.Forbidden:
        await respond(interaction, "타임아웃 해제 실패: 봇 권한을 확인하세요.")


# =========================================================
# 6. 경고
# =========================================================

@bot.tree.command(name="경고", description="멤버에게 경고를 부여합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def 경고(interaction: discord.Interaction, 대상: discord.Member, 사유: str):
    if not await start_command(interaction):
        return

    issue = check_hierarchy(interaction, 대상)
    if issue:
        return await respond(interaction, issue)

    try:
        cursor = db.execute(
            """INSERT INTO warnings
            (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                interaction.guild.id,
                대상.id,
                interaction.user.id,
                사유,
                datetime.now(timezone.utc).isoformat()
            )
        )

        db.commit()

        warning_id = cursor.lastrowid

        count = db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
            (interaction.guild.id, 대상.id)
        ).fetchone()[0]

        await notify_user(대상, f"{interaction.guild.name} 서버에서 경고를 받았습니다.\n사유: {사유}\n누적 경고: {count}회")

        await complete(
            interaction,
            "⚠️ 경고 등록 완료",
            f"대상: {대상.mention}\n경고 번호: #{warning_id}\n누적 경고: {count}회\n사유: {사유}",
            COLOR_ORANGE
        )

    except sqlite3.Error as exc:
        db.rollback()
        print(f"[경고 DB 오류] {exc}")
        await respond(interaction, "경고 저장에 실패했습니다.")


# =========================================================
# 7. 경고 목록
# =========================================================

@bot.tree.command(name="경고목록", description="멤버의 경고 기록을 확인합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def 경고목록(interaction: discord.Interaction, 대상: discord.Member):
    if not await start_command(interaction):
        return

    rows = db.execute(
        """SELECT id, reason, moderator_id, created_at
        FROM warnings
        WHERE guild_id=? AND user_id=?
        ORDER BY id DESC LIMIT 10""",
        (interaction.guild.id, 대상.id)
    ).fetchall()

    count = db.execute(
        "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
        (interaction.guild.id, 대상.id)
    ).fetchone()[0]

    if not rows:
        return await respond(interaction, f"{대상.mention}님의 경고 기록이 없습니다.")

    lines = []

    for warning_id, reason, moderator_id, created_at in rows:
        lines.append(
            f"**#{warning_id}** · {discord.utils.escape_markdown(reason[:180])}\n"
            f"담당자 ID: `{moderator_id}` · {created_at[:19]}"
        )

    embed = make_embed(
        f"📋 {대상.display_name}님의 경고 기록",
        f"누적 경고: **{count}회**\n\n" + "\n\n".join(lines),
        COLOR_PURPLE
    )

    await respond(interaction, embed=embed)


# =========================================================
# 8. 경고 삭제
# =========================================================

@bot.tree.command(name="경고삭제", description="경고 기록을 삭제합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def 경고삭제(interaction: discord.Interaction, 경고번호: app_commands.Range[int, 1, 2147483647]):
    if not await start_command(interaction):
        return

    cursor = db.execute(
        "DELETE FROM warnings WHERE id=? AND guild_id=?",
        (경고번호, interaction.guild.id)
    )

    db.commit()

    if cursor.rowcount == 0:
        return await respond(interaction, "해당 경고 번호를 찾을 수 없습니다.")

    await complete(interaction, "🧹 경고 기록 삭제 완료", f"삭제된 경고 번호: #{경고번호}")


# =========================================================
# 9. 메시지 청소
# =========================================================

@bot.tree.command(name="청소", description="현재 채널의 메시지를 삭제합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
async def 청소(interaction: discord.Interaction, 개수: app_commands.Range[int, 1, 100]):
    if not await start_command(interaction):
        return

    if not await check_bot_permission(interaction, "manage_messages"):
        return

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        return await respond(interaction, "일반 텍스트 채널에서만 사용할 수 있습니다.")

    try:
        deleted = await channel.purge(limit=개수)

        await respond(interaction, f"🧹 메시지 **{len(deleted)}개**를 삭제했습니다.")

        await send_log(
            interaction.guild,
            make_embed(
                "🧹 메시지 청소",
                f"채널: {channel.mention}\n삭제 수: {len(deleted)}개\n담당자: {interaction.user.mention}",
                COLOR_CYAN
            )
        )

    except discord.Forbidden:
        await respond(interaction, "청소 실패: 메시지 관리 권한을 확인하세요.")


# =========================================================
# 10. 슬로우모드
# =========================================================

@bot.tree.command(name="슬로우모드", description="현재 채널의 슬로우모드를 설정합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def 슬로우모드(interaction: discord.Interaction, 초: app_commands.Range[int, 0, 21600]):
    if not await start_command(interaction):
        return

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        return await respond(interaction, "일반 텍스트 채널에서만 사용할 수 있습니다.")

    try:
        await channel.edit(slowmode_delay=초, reason=f"슬로우모드 변경: {interaction.user}")

        label = "해제" if 초 == 0 else f"{초}초"

        await complete(
            interaction,
            "🐢 슬로우모드 설정 완료",
            f"채널: {channel.mention}\n설정: **{label}**",
            COLOR_CYAN
        )

    except discord.Forbidden:
        await respond(interaction, "채널 관리 권한이 없습니다.")


# =========================================================
# 11. 채널 잠금 / 해제
# =========================================================

async def set_channel_lock(interaction: discord.Interaction, locked: bool):
    if not await start_command(interaction):
        return

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        return await respond(interaction, "일반 텍스트 채널에서만 사용할 수 있습니다.")

    try:
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False if locked else None

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"채널 {'잠금' if locked else '잠금 해제'}: {interaction.user}"
        )

        title = "🔒 채널 잠금 완료" if locked else "🔓 채널 잠금 해제 완료"

        await complete(
            interaction,
            title,
            f"채널: {channel.mention}\n담당자: {interaction.user.mention}",
            COLOR_RED if locked else COLOR_GREEN
        )

    except discord.Forbidden:
        await respond(interaction, "실패: 봇에게 채널 관리 권한이 없습니다.")


@bot.tree.command(name="잠금", description="현재 채널을 잠급니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def 잠금(interaction: discord.Interaction):
    await set_channel_lock(interaction, True)


@bot.tree.command(name="잠금해제", description="현재 채널 잠금을 해제합니다.", guild=GUILD_OBJECT)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def 잠금해제(interaction: discord.Interaction):
    await set_channel_lock(interaction, False)


# =========================================================
# 실행
# =========================================================

if __name__ == "__main__":
    try:
        print("[시작] 서버 관리 봇을 실행합니다.")
        bot.run(TOKEN)

    except discord.LoginFailure:
        print("[로그인 실패] TOKEN을 확인하세요.")

    except KeyboardInterrupt:
        print("[종료] 봇을 안전하게 종료했습니다.")

    except Exception as exc:
        print(f"[치명적 오류] {type(exc).__name__}: {exc}")
        traceback.print_exc()

    finally:
        db.close()
