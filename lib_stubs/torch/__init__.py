__version__ = '2.3.0'

# Stub classes needed by datasets/dill serialization internals.
class Tensor: pass
class Generator: pass
class dtype: pass
class device: pass
class Size: pass
class storage: pass

class nn:
    class Module: pass
    class Parameter: pass

class cuda:
    class Stream: pass

# Auto-return a dummy class for any other attribute access so dill
# issubclass/isinstance checks don't raise AttributeError.
class _Stub:
    pass

def __getattr__(name: str):
    return _Stub
