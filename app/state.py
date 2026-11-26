"""Estado en memoria: video cargado, resultados y trabajos."""
STATE = {"video": None, "W": 0, "H": 0, "dur": 0.0, "quality": "", "results": [], "curve": None}
JOBS = {}
CANCELLED = set()
PROCESSES = {}
LOAD_PROGRESS = {"active": False, "percent": 0, "message": ""}
LOAD_CANCEL = {"requested": False}

import time as _time
LAST_ACTIVITY = _time.time()
IDLE = False
IDLE_MINUTES = 10
