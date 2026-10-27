"""
TechnoFunda Swing Bot - Automated Indian Stock Market Swing Trading Backend.
"""

import sys
try:
    import numpy as np
    import numpy.core.records as _rec
    np.rec = _rec
    sys.modules['numpy.rec'] = _rec
except Exception:
    pass

__version__ = "1.0.0"
