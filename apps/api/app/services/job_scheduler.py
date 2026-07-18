"""Заглушка планировщика: реальная реализация появляется в следующей задаче."""


class _NullScheduler:
    def reschedule_job(self, job) -> None:
        return None


scheduler = _NullScheduler()
