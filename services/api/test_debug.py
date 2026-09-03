import asyncio, os, json, numpy as np
os.environ['CELERY_TASK_ALWAYS_EAGER'] = '1'
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./test.db'
os.environ['DATA_DIR'] = './test_data'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['CORS_ORIGINS'] = '["http://localhost:3000"]'

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.auth import create_access_token, hash_password
from app.main import app
from app.database import get_db
from app.models import Base, User
import uuid

engine = create_async_engine('sqlite+aiosqlite:///./test.db', echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with SessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        user = User(id=uuid.uuid4(), email='raw@example.com', password_hash=hash_password('pass'))
        session.add(user)
        await session.commit()
        user_id = user.id

    token = create_access_token(str(user_id))
    headers = {'Authorization': f'Bearer {token}'}

    samples = (np.random.randn(4000) + 1j * np.random.randn(4000)).astype(np.complex64) * 0.1
    interleaved = np.empty(len(samples) * 2, dtype=np.int16)
    interleaved[0::2] = (samples.real * 32767).astype(np.int16)
    interleaved[1::2] = (samples.imag * 32767).astype(np.int16)
    raw_bytes = interleaved.tobytes()
    raw_iq_params = json.dumps({"dtype": "int16", "layout": "interleaved", "endian": "little", "sample_rate_hz": 1000000.0})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        resp = await client.post(
            '/api/recordings/upload',
            headers=headers,
            files={'file': ('signal.iq', raw_bytes, 'application/octet-stream')},
            data={'loader': 'raw_iq', 'raw_iq_params': raw_iq_params},
        )
        print('Status:', resp.status_code)
        print('Body:', resp.text[:2000])

asyncio.run(main())
