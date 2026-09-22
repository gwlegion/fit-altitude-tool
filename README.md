# FIT Altitude Tool 🛰️⛰️

**FIT Altitude Tool** est une application Desktop Python permettant d'enrichir facilement les fichiers d'activités sportives au format `.FIT` (Garmin, Amazfit, Wahoo, etc.) avec des altitudes précises issues du modèle d'élévation **Copernicus GLO-30 (COP30)** via l'API **OpenTopography**.

L'application préserve l'intégralité des métriques d'origine (fréquence cardiaque, cadence, puissance, etc.) et ne modifie que les altitudes manquantes ou imprécises de vos traces GPS.

---

## ✨ Fonctionnalités

- 📁 **Glisser-Déposer (Drag & Drop)** : Déposez directement vos fichiers `.fit` ou dossiers complets dans l'interface.
- 🗺️ **Modèle Copernicus COP30 (30m)** : Récupération des altitudes haute résolution basées sur le modèle altimétrique global Copernicus.
- ⚡ **Cache Local SQLite & Interpolation** : Les tuiles altimétriques brutes GeoTIFF sont conservées en cache local (`%LOCALAPPDATA%\FITAltitudeTool\altitude_cache.db`). L'altitude exacte est calculée localement par interpolation bilinéaire sans requêtes inutiles.
- 🔑 **Gestion Intégrée de la Clé API** : Guide pas-à-pas et assistant d'enregistrement pour la clé OpenTopography stockée en toute sécurité.
- 📦 **Exécutable Windows Autonome** : Compilation simple en un seul fichier `.exe` via PyInstaller sans dépendances requises pour l'utilisateur final.

---

## 📁 Structure du Projet

```text
fit-altitude-tool/
├── app.py                 # Point d'entrée de l'application Tkinter
├── build_exe.bat          # Script d'auto-compilation Windows (.exe)
├── FIT Altitude Tool.spec # Fichier de spécification PyInstaller
├── requirements.txt       # Dépendances Python
├── LICENSE                # Licence Open-Source (MIT)
├── README.md              # Documentation
├── src/                   # Code source de l'application
│   ├── __init__.py
│   ├── ui.py              # Interface graphique (Tkinter/TkinterDND)
│   ├── fit_processor.py   # Lecture, traitement et écriture des fichiers FIT
│   ├── altitude_provider.py# Interaction avec OpenTopography & interpolation
│   ├── cache.py           # Base SQLite locale & gestion des cellules GeoTIFF
│   └── settings.py        # Gestion de la configuration utilisateur
└── tests/                 # Tests unitaires automatisés
    └── test_fit_processor.py
```

---

## 🚀 Installation & Lancement (Mode Développement)

### Prérequis
- **Python 3.10+** (recommandé)

### 1. Cloner le dépôt et installer les dépendances
```powershell
git clone https://github.com/votre-utilisateur/fit-altitude-tool.git
cd fit-altitude-tool

# Créer un environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Lancer l'application
```powershell
python app.py
```

---

## 🔑 Obtenir et Configurer une Clé API OpenTopography

L'accès aux données altimétriques COP30 nécessite une clé API personnelle gratuite auprès d'**OpenTopography** :

1. Créez un compte gratuit sur [portal.opentopography.org](https://portal.opentopography.org/myopentopo).
2. Rendez-vous dans **MyOpenTopo** > **myTopography Authorizations / API Key**.
3. Générez votre clé API.
4. Dans l'application, allez dans **Options > Clé API OpenTopography...**, collez votre clé et cliquez sur **Enregistrer**.

> *Note : Vous pouvez aussi définir la variable d'environnement `OPENTOPO_API_KEY`.*

---

## 🛠️ Générer l'Exécutable Windows (`.exe`)

Pour compiler l'application en un fichier `.exe` autonome (situé dans le dossier `dist/`) :

```powershell
.\build_exe.bat
```

---

## 🧪 Exécuter les Tests Unitaires

```powershell
py -m unittest discover tests
```

---

## 📜 Licence & Attributions

Ce projet est distribué sous licence [MIT](LICENSE).

- **Données d'élévation** : Copernicus DEM GLO-30 fourni par l'Agence Spatiale Européenne (ESA).
- **Service API** : [OpenTopography](https://opentopography.org/). Merci de respecter les conditions d'utilisation d'OpenTopography et de citer leurs services dans vos projets dérivés.
