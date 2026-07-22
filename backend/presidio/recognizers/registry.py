# registry.py
# Collects all custom PatternRecognizers and registers them with a Presidio
# AnalyzerEngine instance. Called once at startup by presidio_engine.py.
#
# custom_recognizers added here (was missing from the original POC's
# registry.py, which left VEHICLE_NUMBER etc. permanently unregistered).

from .personal import get_recognizers as personal_recognizers
from .banking import get_recognizers as banking_recognizers
from .infrastructure import get_recognizers as infrastructure_recognizers
from .security import get_recognizers as security_recognizers
from .custom_recognizers import get_recognizers as custom_recognizers

_MODULES = (
    personal_recognizers,
    banking_recognizers,
    infrastructure_recognizers,
    security_recognizers,
    custom_recognizers,
)


def register_all(analyzer):
    for get_recognizers in _MODULES:
        for recognizer in get_recognizers():
            analyzer.registry.add_recognizer(recognizer)
