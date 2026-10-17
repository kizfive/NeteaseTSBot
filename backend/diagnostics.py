"""Bounded, administrator-only deployment checks. Never return upstream errors or credentials."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .runtime_config import DEFINITION_BY_KEY, get_value, settings_payload, voice_config_revision
from .voice_client import VoiceClient


def _check(id_: str, label: str, status: str, detail: str, action: str = "", *, group: str = "backend", required: bool = True) -> dict[str, Any]:
    return {"id": id_, "label": label, "status": status, "detail": detail, "action": action, "group": group, "required": required}


async def _voice_checks(voice: VoiceClient, expected_revision: str) -> list[dict[str, Any]]:
    try:
        status = await asyncio.wait_for(voice.get_status(), timeout=3)
    except Exception:
        return [
            _check("voice", "Voice 服务", "error", "后端无法在 3 秒内读取语音服务状态。", "检查 Voice 服务是否运行、gRPC 地址和容器网络；Docker 部署使用 voice-service:50051。"),
            _check("teamspeak", "TeamSpeak 连接", "warning", "语音服务离线，暂时无法检查 TeamSpeak 连接。", "先恢复 Voice 服务，再重新检查。", group="teamspeak"),
        ]
    checks = [_check("voice", "Voice 服务", "success", "后端已成功读取语音服务状态。")]
    if expected_revision and getattr(status, "config_revision", "") != expected_revision:
        checks.append(_check("voice_config", "配置应用", "warning", "Voice 尚未确认当前配置版本。", "稍候重试；若一直未更新，检查共享配置文件挂载和 Voice 重启日志。"))
    connected = getattr(status, "teamspeak_connected", None)
    if connected is True:
        checks.append(_check("teamspeak", "TeamSpeak 连接", "success", "语音服务已报告 TeamSpeak 会话连接成功。连接成功不代表已验证目标频道或实际音频播放。", group="teamspeak"))
    elif connected is False:
        checks.append(_check("teamspeak", "TeamSpeak 连接", "error", "Voice 正在运行，但尚未连接 TeamSpeak。", "检查服务器地址、语音 UDP 端口、服务器及频道密码、身份权限与防火墙，再查看 Voice 日志。", group="teamspeak"))
    else:
        checks.append(_check("teamspeak", "TeamSpeak 连接", "warning", "当前 Voice 版本不提供 TeamSpeak 连接状态。", "更新 Voice 服务，或在 TeamSpeak 客户端确认机器人是否已进入目标频道。", group="teamspeak"))
    return checks


async def _netease_check(base_url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
            response = await client.get(f"{base_url.rstrip('/')}/search/default")
            response.raise_for_status()
            data = response.json()
            # A reachable HTML page or an arbitrary JSON service is not a music API.
            if not isinstance(data, dict) or data.get("code") != 200 or not isinstance(data.get("data"), dict):
                raise ValueError("unexpected API response")
        return _check("netease", "网易云 API（可选）", "success", "音乐 API 返回了有效响应；此检查不验证账号权限或歌曲可播放性。", group="music", required=False)
    except Exception:
        return _check("netease", "网易云 API（可选）", "warning", "音乐 API 不可访问或返回格式不符合预期。QQ 音乐和 B 站不依赖它。", "使用网易云时请检查服务地址和部署状态；容器内的 127.0.0.1 指向该容器自身。", group="music", required=False)


async def run_diagnostics(session: Session, voice: VoiceClient) -> dict[str, Any]:
    checks = []
    try:
        session.execute(text("SELECT 1"))
        checks.append(_check("backend", "后端与数据库", "success", "管理员会话和数据库读取正常。"))
        pending = settings_payload(session)["apply_pending"]
        netease_url = str(get_value(session, DEFINITION_BY_KEY["backend.netease_api_base"]))
    except Exception:
        return {"ready": False, "checks": [_check("backend", "后端配置与数据库", "error", "无法读取数据库或运行配置。", "检查数据目录权限、数据库状态，以及升级后是否保留原加密密钥。") ]}
    if pending:
        checks.append(_check("pending", "配置应用", "warning", "有已保存但尚未应用的配置。", "点击“应用并检查”后重新检查连接。"))
    if not settings.cookie_key or settings.cookie_key in {"dev-cookie-key", "replace_with_a_long_random_key"}:
        checks.append(_check("encryption", "启动加密密钥", "warning", "仍在使用默认加密密钥。", "新安装请在 tsbot.env 设置自己的 TSBOT_COOKIE_KEY；已有加密数据不要直接更换密钥。", required=False))
    voice_checks, music_check = await asyncio.gather(_voice_checks(voice, voice_config_revision()), _netease_check(netease_url))
    checks.extend(voice_checks)
    checks.append(music_check)
    return {"ready": all(item["status"] == "success" for item in checks if item["required"]), "checks": checks}
