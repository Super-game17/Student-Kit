# Local Ollama PDF Processing Pipeline with Streamlit & Modular Python

StudentKit est une démonstration technique locale d'une pipeline Python
modulaire : extraction de texte PDF, préparation de contexte, génération
structurée avec Ollama, validation des sorties et interface Streamlit.

Le projet est volontairement conçu comme un exemple d'ingénierie logicielle
exécutable localement, sans compte utilisateur, service cloud obligatoire ni
clé API versionnée.

## Points techniques démontrés

- **Architecture modulaire** : interface, domaine, stockage, traitement PDF,
  client IA et exports sont séparés.
- **Injection de dépendances** : `generate_flashcards` et `generate_quiz`
  acceptent un `AIClient`, ce qui permet de remplacer Ollama par le mode démo
  ou un faux client de test sans modifier la logique métier.
- **Contrat IA interchangeable** : `AIClient` définit l'interface commune ;
  `OllamaClient` gère l'appel HTTP local et `DemoClient` fournit une exécution
  déterministe sans réseau.
- **Validation défensive** : les réponses JSON sont vérifiées avant usage,
  les cartes et QCM doivent respecter leur schéma, et les réponses invalides
  sont refusées plutôt que présentées comme fiables.
- **Gestion des erreurs d'inférence** : timeouts, service Ollama indisponible,
  JSON mal formé, réponses enveloppées et structures incompatibles produisent
  des erreurs explicites.
- **Algorithme déterministe** : le planner ne délègue pas la décision à l'IA.
  Les priorités et les sessions sont reproductibles et testables.
- **Tests unitaires pytest** : cas nominaux, limites de dates et disponibilités,
  validation JSON, extraction PDF, stockage local et réponses IA invalides.

## Architecture

```text
app.py                         Interface Streamlit et orchestration
student_kit/
├── core/
│   ├── ai_client.py           AIClient, OllamaClient, DemoClient
│   ├── exporters.py           Exports ReportLab PDF et CSV
│   ├── flashcards.py          Validation, génération et révision
│   ├── pdf_reader.py          Extraction et découpage PDF
│   ├── planner.py             Priorités et planning déterministes
│   └── storage.py             Persistance JSON atomique
└── tests/
    ├── test_planner.py        Tests du moteur de planification
    └── test_study.py          Tests PDF, IA, QCM et flashcards
```

### Flux de traitement

1. `pdf_reader.py` extrait et valide le texte avec `pypdf`.
2. Le texte long est découpé en morceaux avec chevauchement.
3. Un fournisseur implémentant `AIClient` reçoit un prompt borné au contenu.
4. `flashcards.py` parse et valide la réponse JSON.
5. Les cartes et résultats peuvent être persistés dans le fichier local.
6. `exporters.py` produit un PDF de planning ou un CSV de flashcards.

Les documents ne sont envoyés à Ollama qu'après l'action explicite de
génération dans l'interface. Ollama reste local ; aucune clé API n'est
nécessaire.

## Installation

Depuis la racine du dépôt :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Exécution

### Mode démonstration

Le mode par défaut ne contacte aucun service externe :

```powershell
$env:AI_PROVIDER = "demo"
streamlit run app.py
```

Les données simulées sont clairement produites à partir du texte fourni et ne
sont pas présentées comme une inférence fiable.

### Ollama local

1. Installer et démarrer Ollama.
2. Télécharger un modèle local, par exemple :

```powershell
ollama pull llama3.2
```

3. Configurer le fournisseur :

```powershell
$env:AI_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "llama3.2"
streamlit run app.py
```

Les variables peuvent aussi être placées dans un fichier `.env` local à partir
de [.env.example](./.env.example). Ce fichier ne doit jamais être commité.

## Tests

```powershell
python -m pytest -q
```

Les tests n'exigent pas Ollama : les fournisseurs sont injectés et les cas
d'erreur sont simulés par des clients de test.

## Planner déterministe

Le planner calcule les priorités selon l'urgence, la difficulté, le volume
restant et le niveau de maîtrise. Il respecte les disponibilités quotidiennes
et génère des sessions de 50 minutes avec 10 minutes de pause.

Les cas limites couverts sont :

- examens passés ou le jour même ;
- examens multiples ;
- disponibilité nulle ;
- volume restant nul ;
- planning vide ;
- résultat reproductible pour les mêmes entrées.

## Stockage local et exports

`StudentStorage` écrit atomiquement les données dans
`data/student_data.json`. Le fichier est ignoré par Git et contient les
matières, examens, disponibilités, sessions et flashcards.

L'interface permet :

- l'export du planning au format PDF avec ReportLab ;
- l'export des flashcards au format CSV UTF-8 ;
- la conservation locale des évaluations de révision.

Pour supprimer les données locales :

```powershell
Remove-Item .\data\student_data.json
```

## Limites techniques assumées

- Ollama peut produire une réponse factuellement incorrecte ; la validation
  de schéma ne remplace pas une vérification humaine.
- Le mode démo est un mécanisme de démonstration, pas un modèle de langage.
- Les PDF scannés sans couche texte nécessitent une OCR, qui n'est pas incluse
  dans ce périmètre.
- Le stockage est local et mono-utilisateur ; aucune synchronisation distante
  n'est implémentée.

## Licence

Aucune licence n'est définie pour le moment. Ajouter une licence explicite
avant toute redistribution publique.
