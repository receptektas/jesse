import json
import os
import warnings
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jesse.services.web import fastapi_app
import jesse.helpers as jh

# import cli to register the routes. Do NOT remove this import.
from jesse.cli import cli


# Suppress pandas FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# get the jesse directory
JESSE_DIR = os.path.dirname(os.path.abspath(__file__))

ACTIVE_CONFIG_FILE = '.active-backtest-config'
DEFAULT_WARM_UP_CANDLES = 210

# Active preset form config — populated at startup, served via /api/active-preset
_active_form_config: dict | None = None


def _load_preset(config_name: str) -> dict | None:
    if config_name.endswith('.json'):
        config_name = config_name[:-5]
    config_path = os.path.join('backtest-configs', f'{config_name}.json')
    if not os.path.exists(config_path):
        print(f'[WARN] Backtest config not found: {config_path}')
        return None
    print(f'[PRESET] Loading preset from: {config_path}')
    with open(config_path) as f:
        return json.load(f)


def _build_form_config(preset: dict) -> dict:
    return {
        'routes': preset.get('routes', []),
        'extra_routes': preset.get('extra_routes', []),
        'start_date': preset.get('start_date', ''),
        'finish_date': preset.get('finish_date', ''),
        'fast_mode': preset.get('fast_mode', False),
        'benchmark': preset.get('benchmark', False),
        'debug_mode': preset.get('debug_mode', False),
        'export_chart': preset.get('export_chart', False),
        'export_tradingview': preset.get('export_tradingview', False),
        'export_csv': preset.get('export_csv', False),
        'export_json': preset.get('export_json', False),
        'export_full_reports': preset.get('export_full_reports', False),
        'warm_up_candles': preset.get('warm_up_candles', DEFAULT_WARM_UP_CANDLES),
    }


def _apply_exchange_settings(preset: dict, config_name: str) -> None:
    import peewee
    from jesse.models.Option import Option

    try:
        o = Option.get(Option.type == 'config')
        db_config = json.loads(o.json)

        exchanges = db_config.get('backtest', {}).get('exchanges', {})
        for exchange_name, settings in preset.get('exchange_settings', {}).items():
            if exchange_name in exchanges:
                exchanges[exchange_name].update(settings)
            else:
                print(f'[PRESET] Skipping "{exchange_name}" — not found in DB config')

        if 'warm_up_candles' in preset:
            db_config['backtest']['warm_up_candles'] = preset['warm_up_candles']

        o.json = json.dumps(db_config)
        o.updated_at = jh.now(True)
        o.save()
        print(f'[PRESET] Exchange settings applied for "{config_name}"')
    except peewee.DoesNotExist:
        print(f'[PRESET] DB record not found yet — exchange settings will apply after first UI save')


def _apply_form_config_to_sessions(form_config: dict) -> None:
    from jesse.models.BacktestSession import BacktestSession

    sessions = list(BacktestSession.select())
    for session in sessions:
        existing_state = json.loads(session.state) if session.state else {}
        existing_state['form'] = {**existing_state.get('form', {}), **form_config}
        BacktestSession.update(
            state=json.dumps(existing_state),
            updated_at=jh.now_to_timestamp(True)
        ).where(BacktestSession.id == session.id).execute()
    print(f'[PRESET] Updated {len(sessions)} backtest session(s) with form config')


def _apply_active_backtest_config() -> None:
    global _active_form_config

    if not os.path.exists(ACTIVE_CONFIG_FILE):
        print(f'[PRESET] No active config file found')
        return

    with open(ACTIVE_CONFIG_FILE) as f:
        config_name = f.read().strip()

    if not config_name:
        return

    print(f'[PRESET] Active config: {config_name}')

    preset = _load_preset(config_name)
    if preset is None:
        return

    form_config = _build_form_config(preset)

    from jesse.services.db import database
    database.open_connection()
    try:
        _apply_exchange_settings(preset, config_name)
        _apply_form_config_to_sessions(form_config)
    except Exception as e:
        print(f'[WARN] Could not update DB from preset: {e}')
    finally:
        database.close_connection()

    _active_form_config = form_config


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
    return HTMLResponse(content=open(f"{JESSE_DIR}/static/index.html").read())


@fastapi_app.get("/api/active-preset")
async def active_preset():
    return JSONResponse(_active_form_config or {})


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
