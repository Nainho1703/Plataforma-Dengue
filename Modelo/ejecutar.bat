@echo off
call conda activate licitacion

cd "C:\Users\Nainh\Proton Drive\nainho1306\My files\Licitacion\Plataforma local\Modelo\codigos_varios\Clima\clima copernico"
papermill leer_clima2.ipynb NUL

cd ..
cd ..
papermill preprocesar_datos_mejor.ipynb NUL
papermill modelo_new.ipynb NUL

pause
