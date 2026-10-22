"""The Android worker delegates sync to the unlocked runtime's event-loop thread."""
import asyncio
import threading

from lightning.runtime import journal_android


def test_android_sync_only_uses_registered_unlocked_runtime(tmp_path):
    assert asyncio.run(journal_android.sync_once(tmp_path)) == "locked"


def test_android_worker_awaits_on_the_runtime_loop_and_unregisters_by_identity(tmp_path):
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    loop_thread_id = []

    def run_loop():
        asyncio.set_event_loop(loop)
        loop_thread_id.append(threading.get_ident())
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop)
    thread.start()
    assert ready.wait(2)
    old_runtime, runtime = object(), object()
    seen = []

    async def synchronize():
        seen.append(threading.get_ident())
        return "synced"

    try:
        journal_android.register(tmp_path, old_runtime, loop, synchronize)
        journal_android.register(tmp_path, runtime, loop, synchronize)
        journal_android.unregister(tmp_path, old_runtime)
        assert asyncio.run(journal_android.sync_once(tmp_path)) == "synced"
        assert seen == loop_thread_id
        journal_android.unregister(tmp_path, runtime)
        assert asyncio.run(journal_android.sync_once(tmp_path)) == "locked"
    finally:
        journal_android.unregister(tmp_path, runtime)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(2)
        loop.close()
