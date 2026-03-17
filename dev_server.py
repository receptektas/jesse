"""
Dev server: jesse run ile aynı işlemi yapar ama uvicorn --reload ile başlatır.
"""
import os
import sys
import time

# Proje dizininde çalıştığımızdan emin ol
os.chdir('/project')
sys.path.insert(0, '/jesse-docker')

if __name__ == '__main__':
    # DB migrations
    import peewee
    from jesse.services.migrator import run as run_migrations

    try:
        print("Running DB migrations...")
        run_migrations()
    except peewee.OperationalError:
        print("Database not ready, retrying in 10 seconds...")
        time.sleep(10)
        run_migrations()

    print("Starting Jesse dev server (hot-reload active)...")

    import uvicorn

    uvicorn.run(
        "jesse.services.web:fastapi_app",
        host="0.0.0.0",
        port=9000,
        reload=True,
        reload_dirs=["/jesse-docker/jesse"],
        log_level="info",
    )
