# 🎸 SoundPass — Sistema de Ticketing para Conciertos

Proyecto universitario construido con **Flask + MySQL (XAMPP)**.

---

## 📁 Estructura del proyecto

```
concert_tickets/
├── app.py                  ← Lógica principal de Flask
├── requirements.txt        ← Dependencias Python
├── database.sql            ← Script SQL para crear tablas
├── templates/
│   ├── index.html          ← Página de compra (usuario)
│   ├── confirmacion.html   ← Confirmación tras la compra
│   └── admin.html          ← Panel de validación (staff)
└── static/                 ← (para CSS/JS/img propios si los necesitas)
```

---

## ⚙️ Pasos para ejecutar el proyecto

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Iniciar XAMPP
- Abre el **XAMPP Control Panel**
- Inicia **Apache** y **MySQL**
- Ve a: http://localhost/phpmyadmin

### 3. Crear la base de datos
- En phpMyAdmin → pestaña **SQL**
- Pega el contenido de `database.sql` y haz clic en **Ejecutar**

### 4. Configurar el correo en app.py
Edita estas dos líneas en `app.py`:
```python
EMAIL_REMITENTE = "tuemail@gmail.com"
EMAIL_APP_PASS  = "xxxx xxxx xxxx xxxx"  # App Password de Gmail
```

### 5. Ejecutar la aplicación
```bash
python app.py
```
Abre: **http://127.0.0.1:5000**

---

## 🔑 Cómo obtener el App Password de Gmail

> **¿Por qué?** Gmail NO permite usar tu contraseña normal para apps externas.
> Debes generar una "Contraseña de Aplicación" de 16 caracteres.

**Pasos:**
1. Ve a tu cuenta Google → https://myaccount.google.com
2. Busca **"Seguridad"** en el menú lateral
3. Activa la **Verificación en 2 pasos** (si no está activa, es obligatorio)
4. Vuelve a Seguridad → busca **"Contraseñas de aplicaciones"**
5. En "Seleccionar app" elige **Otro (nombre personalizado)** → escribe "Flask Concert"
6. Haz clic en **Generar**
7. Copia la clave de 16 caracteres (ej: `abcd efgh ijkl mnop`)
8. Pégala en `app.py` en la variable `EMAIL_APP_PASS`

---

## 🌐 Rutas de la aplicación

| Ruta        | Método   | Descripción                          |
|-------------|----------|--------------------------------------|
| `/`         | GET      | Formulario de compra de ticket       |
| `/comprar`  | POST     | Procesa la compra y guarda en DB     |
| `/admin`    | GET      | Panel de validación para el staff    |
| `/validar`  | POST     | Verifica y marca un código de ticket |

---

## 🛡️ Lógica de validación de tickets

```
Staff ingresa código
        │
        ▼
¿Existe en DB?
   No  → ❌ "Ticket inválido"
   Sí  → ¿Estado == 'Ingresado'?
              Sí → ⚠️  "Ya fue utilizado"
              No → ✅  Marcar como 'Ingresado' → "Acceso permitido"
```

---

## 📧 Flujo del correo electrónico

```
Usuario compra → UUID generado → Guardado en DB
                                        │
                              threading.Thread() iniciado
                                        │
                              smtplib envía correo HTML
                              (sin bloquear la respuesta web)
```