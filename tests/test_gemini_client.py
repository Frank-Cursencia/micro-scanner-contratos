import asyncio

from app.config import get_settings
from app.services.gemini_client import _semaphore


def test_semaphore_caps_concurrency_at_configured_limit():
    get_settings.cache_clear()
    _semaphore.cache_clear()
    limit = get_settings().gemini_max_concurrency

    async def scenario():
        sem = _semaphore()

        async def hold():
            async with sem:
                await asyncio.sleep(0.05)

        tasks = [asyncio.create_task(hold()) for _ in range(limit + 1)]
        await asyncio.sleep(0.01)
        assert sem._value == 0  # todos los slots ocupados, el (limit+1)-ésimo espera
        await asyncio.gather(*tasks)
        assert sem._value == limit  # se liberaron todos al terminar

    asyncio.run(scenario())
