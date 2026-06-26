"""SQLite 영속화 레이어 (aiosqlite).

현재는 목표값(settings) 저장만 담당한다.
Phase 3에서 sensor_logs 테이블/조회 함수를 같은 컨벤션으로 이 파일에 추가한다.
"""
import os

import aiosqlite

from config import DB_PATH, DEFAULT_TARGET_EC, DEFAULT_TARGET_PH


async def init_db() -> None:
    """DB 파일·디렉터리 생성, settings 테이블 생성, 목표값 기본 시드."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      REAL NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 행이 없을 때만 config 기본값으로 시드
        await db.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("target_ec", DEFAULT_TARGET_EC),
                ("target_ph", DEFAULT_TARGET_PH),
            ],
        )
        await db.commit()


async def get_target() -> dict:
    """목표값 조회. 행이 없으면 config 기본값으로 fallback."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT key, value FROM settings WHERE key IN ('target_ec', 'target_ph')"
        ) as cur:
            rows = {key: value for key, value in await cur.fetchall()}

    return {
        "ec": rows.get("target_ec", DEFAULT_TARGET_EC),
        "ph": rows.get("target_ph", DEFAULT_TARGET_PH),
    }


async def set_target(ec: float, ph: float) -> dict:
    """목표값 upsert 후 저장된 값 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                ("target_ec", ec),
                ("target_ph", ph),
            ],
        )
        await db.commit()

    return {"ec": ec, "ph": ph}
