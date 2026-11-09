# ADR-0002 — Upstream-sync per client in branch `sync/<client>-<tag>`

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** B03-013 vraagt een minimale patch stack, beschermde CI en een bewaakt upgradepad; EX48 eist dat een
  incompatibele upstream-update faalt zonder productie-deploy. Clients hebben elk een eigen releaseritme.

## Besluit

1. **Per client apart.** `tools/clients/upstream_sync.py status` vergelijkt per client de basislijn-tag met de nieuwste
   stabiele upstream-tag (`git ls-remote`, filter `tag_patroon` uit de basislijn; pre-releases tellen niet). Een
   netwerkfout geeft `unknown`, nooit `actueel`.
2. **Sync = subtree pull met squash in een eigen branch.** `upstream_sync.py sync <client> [--tag T]`:
   - weigert bij een vuile werkboom of een bestaande syncbranch;
   - haalt de tag en de vorige upstream-commit op (nodig voor de squash in een verse clone);
   - maakt branch `sync/<client>-<tag>` en doet `git subtree merge --prefix <map> --squash <tag-commit>` (inhoudelijk
     gelijk aan `git subtree pull --prefix <map> --squash <upstream-url> <tag>`);
   - volgt een gewijzigde submodule-pin met de geneste subtree (ADR-0005);
   - werkt `baseline.json` bij (tag, commit, forkversie `<upstream>-jl.0`) en draait `check_clients.py`.
3. **Falen is veilig.** Elk ander mergeconflict, een nieuwe of verdwenen submodule, of een geschonden forkregel
   (bv. upstream nam onze patch over en het register is verouderd) → volledige terugdraaiing (oorspronkelijke branch,
   syncbranch weg, werkboom schoon) en **exitcode 2**. Niets wordt gepusht.
4. **Workflow** `clients-upstream-sync.yml` (wekelijks + handmatig): per client de herbruikbare sync, push van alleen
   `sync/<client>-<tag>` (bestaat die al op origin → niet overschrijven), daarna forkregels + client-CI op die branch.
5. **Overnemen is een mens (R2).** Samenvoegen met de hoofdbranch en elke release/APK-distributie zijn handmatige
   stappen na review en groene CI. De workflow maakt geen PR, merge, tag, release of image.

## Gevolgen

- Gemeten op echte upstream-code: desktop v2.0.0 → master (214 commits) schoon in een verse clone
  (`docs/platform-v2/test-evidence/p0-syncproef-desktop-master.json`).
- `schedule` draait bij GitHub alleen vanaf de standaardbranch; tot deze branch daar staat, alleen handmatig.
- Pushen gebeurt met `GITHUB_TOKEN`; daardoor start GitHub geen push-workflows op de syncbranch — de sync-workflow roept
  de CI daarom zelf aan (`workflow_call`).
- Terugzetten van een overgenomen sync = de squash-merge terugdraaien (`git revert -m 1`), basislijn mee.
