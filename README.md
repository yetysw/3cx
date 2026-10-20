# 3cx — outils pour PBX 3CX

Petite boîte à outils autour de l'API XAPI de 3CX (v20+).

| Outil | Rôle |
|---|---|
| [`src/outbound_selector`](src/outbound_selector) | App desktop (tkinter) : choisir le numéro sortant d'une extension sans taper de préfixe |
| [`tools/holidays_hours`](tools/holidays_hours) | Script : horaires de bureau et jours fériés par département *(work in progress)* |

## Outbound selector

Quand un PBX a beaucoup de numéros sortants, chacun lié à une règle sortante avec un préfixe (`101`, `102`…), il faut taper le bon préfixe avant chaque appel. L'app affiche les entreprises sous forme de cartes :

- **Copier** : copie le préfixe dans le presse-papier.
- **Utiliser** : change directement l'`OutboundCallerID` de l'extension via l'API.
- **Auto-reset** : après 60 s, l'extension revient sur son numéro par défaut.

### Installation

Python 3.12+.

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml    # puis renseigner url, username, mapping
python src/outbound_selector/outbound_selector.py
```

Le mot de passe peut rester hors du fichier : `THREECX_PASSWORD` (variable d'environnement) est utilisée si `pbx.password` est vide.

### Configuration

`config.yaml` est cherché à côté du script (ou de l'exe). Voir [`config.example.yaml`](config.example.yaml).

L'API XAPI v1 n'expose pas les vrais DID des règles sortantes (`Routes[].CallerID` vide, `TrunkId = -1`). Le mapping `outbound_labels` (clé = `Prefix` exact de la règle) fournit donc les numéros à afficher. Sans mapping, seul **Copier** est proposé.

### Utilisation

- Onglet **Numéro sortant** : extension, actualisation, reset, cartes triées par préfixe.
- Onglet **Config** : entreprise par défaut (cible du reset), extensions et entreprises visibles. Sauvegardé dans `.state.json` (non versionné).

### Build de l'exécutable

```bash
pip install pyinstaller
pyinstaller outbound_selector.spec
```

Résultat : `dist/3CX_OutboundSelector.exe` (portable). Déposer `config.yaml` à côté de l'exe.

### Architecture

```
outbound_selector.py   GUI tkinter
        |
   api_3cx.py          ThreeCXAPI : auth Bearer + GET/PATCH/POST
        |
   3CX XAPI v1         REST OData, HTTPS
```

Les appels réseau tournent dans des threads daemon ; les callbacks UI repassent par `root.after(0, …)`. Les certificats auto-signés sont acceptés (`verify=False`) : à durcir si votre PBX a un certificat valide.

## Holidays & hours

`tools/holidays_hours/configure_hours.py` définit des profils d'horaires et des jours fériés (VS/VD) et les applique aux départements. Identifiants via `THREECX_URL`, `THREECX_USER`, `THREECX_PASSWORD`, `THREECX_SECURITY_CODE`.

```bash
python tools/holidays_hours/configure_hours.py --list
python tools/holidays_hours/configure_hours.py --dry-run
```

> Statut : ancien script, non finalisé. `DEPT_CONFIG` n'est pas encore exploité (le profil A est appliqué à tous les groupes) et les jours fériés ne sont pas envoyés. Utiliser `--dry-run` d'abord.

## Sécurité

Ne jamais committer `config.yaml`, `.state.json` ou des identifiants (voir `.gitignore`).

## Licence

MIT — voir [LICENSE](LICENSE).
