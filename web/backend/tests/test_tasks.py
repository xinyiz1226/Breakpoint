def test_celery_app_configured():
    from app.tasks.celery_app import celery_app
    assert celery_app.main == "breakpoint"


def test_analysis_service_importable():
    from app.services.analysis_service import run_engine_analysis, run_engine_export
    assert callable(run_engine_analysis)
    assert callable(run_engine_export)


def test_tasks_importable():
    from app.tasks.analysis import analyze_video
    from app.tasks.export import export_highlights
    assert callable(analyze_video)
    assert callable(export_highlights)
