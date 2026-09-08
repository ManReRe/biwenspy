# biwenspy

Dashboard financiero para tu liga de Biwenger: dinero disponible, movimientos de mercado y
puntos de cada manager a lo largo de la temporada, reconstruidos desde 20.000.000 EUR iniciales.

## Uso

1. Instala dependencias:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Captura tu sesion (una vez, o cuando el token caduque):
   ```
   python capture_token.py
   ```
3. Sincroniza los datos de la liga (repite cuando quieras datos frescos, es incremental):
   ```
   python sync.py
   ```
4. Genera el dashboard:
   ```
   python dashboard.py
   ```
5. Abre `dashboard.html` en el navegador.

## Tests

```
pytest
```
