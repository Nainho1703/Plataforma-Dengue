#!/usr/bin/env python
# coding: utf-8

# In[4]:


import pandas as pd

df = pd.read_csv(r"data\processed\casos_con_municerca.csv")
df=df[['municerca','casos','fecha_agg']]
df2=df.copy()



# In[ ]:




