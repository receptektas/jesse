import json
import os
import warnings
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jesse.services.web import fastapi_app
import jesse.helpers as jh

# import cli to register the routes. Do NOT remove this import.
from jesse.cli import cli


# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# get the jesse directory
JESSE_DIR = os.path.dirname(os.path.abspath(__file__))

# holds the form config to inject into index.html (set at startup)
_active_form_config = None


def _apply_active_backtest_config():
    global _active_form_config

    active_config_file = '.active-backtest-config'
    if not os.path.exists(active_config_file):
        return

    config_name = open(active_config_file).read().strip()
    if not config_name:
        return

    config_path = os.path.join('backtest-configs', f'{config_name}.json')
    if not os.path.exists(config_path):
        print(f'[WARN] Backtest config not found: {config_path}')
        return

    with open(config_path) as f:
        preset = json.load(f)

    # Update exchange settings and warm_up_candles in DB
    try:
        import peewee
        from jesse.services.db import database
        from jesse.models.Option import Option

        database.open_connection()
        try:
            o = Option.get(Option.type == 'config')
            db_config = json.loads(o.json)

            for exchange_name, settings in preset.get('exchange_settings', {}).items():
                if exchange_name in db_config.get('backtest', {}).get('exchanges', {}):
                    db_config['backtest']['exchanges'][exchange_name].update(settings)

            if 'warm_up_candles' in preset:
                db_config['backtest']['warm_up_candles'] = preset['warm_up_candles']

            o.json = json.dumps(db_config)
            o.updated_at = jh.now(True)
            o.save()
            print(f'[INFO] Applied backtest config "{config_name}" to DB.')
        except peewee.DoesNotExist:
            print(f'[INFO] No DB config record yet; skipping DB update for preset "{config_name}".')
        finally:
            database.close_connection()
    except Exception as e:
        print(f'[WARN] Could not update DB config from preset: {e}')

    # Store form config for HTML injection
    _active_form_config = {
        'routes': preset.get('routes', []),
        'extra_routes': preset.get('extra_routes', []),
        'start_date': preset.get('start_date', ''),
        'finish_date': preset.get('finish_date', ''),
        'debug_mode': preset.get('debug_mode', False),
        'export_chart': preset.get('export_chart', False),
        'export_tradingview': preset.get('export_tradingview', False),
        'export_csv': preset.get('export_csv', False),
        'export_json': preset.get('export_json', False),
        'export_full_reports': preset.get('export_full_reports', False),
    }


# define lifespan (replaces deprecated @on_event("shutdown"))
@asynccontextmanager
async def lifespan(app):
    _apply_active_backtest_config()
    yield
    from jesse.services.db import database
    database.close_connection()
    from jesse.services.lsp import terminate_lsp_server
    terminate_lsp_server()

fastapi_app.router.lifespan_context = lifespan

# load homepage
@fastapi_app.get("/")
async def index():
    html = open(f"{JESSE_DIR}/static/index.html").read()
    if _active_form_config:
        script = f'<script>localStorage.setItem("backtestForm",{json.dumps(_active_form_config)});</script>'
        html = html.replace("</head>", f"{script}\n</head>", 1)
    return HTMLResponse(content=html)






# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Routes
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
from jesse.controllers.websocket_controller import router as websocket_router
from jesse.controllers.optimization_controller import router as optimization_router
from jesse.controllers.monte_carlo_controller import router as monte_carlo_router
from jesse.controllers.exchange_controller import router as exchange_router
from jesse.controllers.backtest_controller import router as backtest_router
from jesse.controllers.candles_controller import router as candles_router
from jesse.controllers.strategy_controller import router as strategy_router
from jesse.controllers.auth_controller import router as auth_router
from jesse.controllers.config_controller import router as config_router
from jesse.controllers.notification_controller import router as notification_router
from jesse.controllers.system_controller import router as system_router
from jesse.controllers.file_controller import router as file_router
from jesse.controllers.lsp_controller import router as lsp_router
from jesse.controllers.closed_trade_controller import router as closed_trade_router
from jesse.controllers.order_controller import router as order_router
from jesse.controllers.tabs_controller import router as tabs_router

# register routers
fastapi_app.include_router(websocket_router)
fastapi_app.include_router(optimization_router)
fastapi_app.include_router(monte_carlo_router)
fastapi_app.include_router(exchange_router)
fastapi_app.include_router(backtest_router)
fastapi_app.include_router(candles_router)
fastapi_app.include_router(strategy_router)
fastapi_app.include_router(auth_router)
fastapi_app.include_router(config_router)
fastapi_app.include_router(notification_router)
fastapi_app.include_router(system_router)
fastapi_app.include_router(file_router)
fastapi_app.include_router(lsp_router)
fastapi_app.include_router(closed_trade_router)
fastapi_app.include_router(order_router)
fastapi_app.include_router(tabs_router)

# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Live Trade Plugin
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
if jh.has_live_trade_plugin():
    from jesse.controllers.live_controller import router as live_router
    fastapi_app.include_router(live_router)


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Static Files (Must be loaded at the end to prevent overlapping with API endpoints)
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
fastapi_app.mount("/", StaticFiles(directory=f"{JESSE_DIR}/static"), name="static")
