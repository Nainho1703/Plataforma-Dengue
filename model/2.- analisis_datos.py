# -*- coding: utf-8 -*-
# Auto-added by exporter: force UTF-8 stdout/stderr when running as .py
import os, sys
try:
    # Python 3.7+: reconfigure disponible en la mayoría de builds
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    else:
        # Fallback: envolver buffers (evita fallar en Jupyter donde no hay .buffer)
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    # Nunca romper el script por temas de encoding
    pass

#!/usr/bin/env python
# coding: utf-8

# In[4]:


import pandas as pd

df = pd.read_csv(r"data\processed\casos_con_municerca.csv")
df=df[['municerca','casos','fecha_agg']]
df2=df.copy()



# In[ ]:




