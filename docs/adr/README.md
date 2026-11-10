# Architectuurbesluiten (ADR) — jelly-leon-clients

| ADR | Onderwerp | Status |
|---|---|---|
| [ADR-0001](ADR-0001-subtree-indeling.md) | Vier clients als git subtree (squash) in één repo | Aanvaard |
| [ADR-0002](ADR-0002-upstream-sync-per-client.md) | Upstream-sync per client in `sync/<client>-<tag>` | Aanvaard |
| [ADR-0003](ADR-0003-patchregister.md) | Patchregister met automatische controle | Aanvaard |
| [ADR-0004](ADR-0004-branding-en-applicationid.md) | Branding alleen zichtbaar; eigen applicationId/bundle-id naast de officiële apps | Aanvaard (besluit gebruiker 2026-11-09); uitgevoerd als JLC-0002/0003/0004 |
| [ADR-0005](ADR-0005-submodules-als-geneste-subtree.md) | Submodules als geneste subtree (mpvqt) | Aanvaard |
| [ADR-0006](ADR-0006-upstream-workflows-en-ci.md) | Upstream-workflows inert, eigen CI in de root | Aanvaard |
| [ADR-0007](ADR-0007-licenties-en-bronbeschikbaarheid.md) | Licenties, credits, bron beschikbaar | Aanvaard; publiek na historiescan (besluit gebruiker) |
| [ADR-0008](ADR-0008-geen-truenas-app-voor-clients.md) | Geen image/Custom App/OpenAPI voor apparaat-apps | Aanvaard (contractpunt) |
| [ADR-0009](ADR-0009-swiftfin-servercompatibiliteit.md) | Swiftfin 1.6.1 blijft; server vóór P4 naar Jellyfin 12.x | Aanvaard (besluit gebruiker 2026-11-09); herbeoordeeld 2026-11-10 tegen 12.4 |
| [ADR-0010](ADR-0010-contract-1-2-in-de-clients.md) | Contract 1.2 in de clients (JC1–JC5), eigen app-identiteit, drifttest | Aanvaard |
| [ADR-0011](ADR-0011-clientcompatibiliteit-12x.md) | Clientcompatibiliteit met de Jelly Leon 12.x-server (JC3): harnas, controlegroep stock, meetregels | Aanvaard (P4-0, 2026-11-10) |

## B03 2.0 — besluiten in jelly-leon die de clients raken (verwijzing)

Het bouwplan B03 2.0 (`../platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md`, door de gebruiker goedgekeurd op
2026-11-09) legt zijn ADR-voorstellen vast in `lvos04/jelly-leon` (`docs/adr/`, ADR-0015…0024) en, voor platformpunten, in
`lvos04/ai-server-manager`. Deze repo neemt ze niet over als eigen ADR; ze gelden hier als randvoorwaarde. De eigen ADR's
hierboven blijven gelden (o.a. ADR-0004 eigen app-identiteit, ADR-0007 licenties, ADR-0009 Swiftfin 1.6.1 tegen 12.x).

| ADR in jelly-leon (voorstel) | Wat het voor de clients betekent | Eigen ADR/werk in deze repo |
|---|---|---|
| ADR-0015 (ADR-B03-01): 12.x-basis en overname van de bestaande mediaserver (Emby) | server en web gaan naar 12.x (legacy-auth uit; derden-clients met legacy-headers komen in de matrix, BG-01); clientmatrix opnieuw tegen 12.x. **Overname vanuit Emby (P0, golf 0):** gebruikers loggen daarna in met een nieuw wachtwoord of SSO en hervatten op het juiste punt (JLT-70; echte NAS JLT-74 *Geblokkeerd*) | ADR-0009; B03-014, B03-016, B03-019 |
| ADR-0019 (ADR-B03-07): register van upstream-gedrag, patches en webhaken | clientpatches alleen voor de eigen apps, klein en per subtree herbaseerbaar; geen patches in Swiftfin in v1; sync-proef per patch (JLT-67) | ADR-0002, ADR-0003 (patchregister JLC-…) |
| ADR-0022 (ADR-B03-10): post-credit-bescherming met segmentgrenzen | geen nieuw segmenttype; de bescherming werkt in elke client die naar `EndTicks` springt, ook stock-clients; standaard "vragen", nooit automatisch overslaan; per client getest (JLT-51, JLT-55) | B03-007, B03-077 |
| ADR-0023 (ADR-B03-11): licentiebeleid voor code, modellen en testdata | geldt voor alle B03-repos: geen AGPL, NC-modellen nooit, beperkt gelicentieerde testdata alleen lokaal (CI-guard) | ADR-0007 |
| ADR-0024 (ADR-B03-12): clientrollen | vijf rollen (stock-native, stock-web, officiële app met serverweb, Jelly Leon-webclient, fork-app); stock-clients worden nooit geweigerd of aangepast zonder opt-in; tests per rol (JLT-46, JLT-63) | ADR-0004; B03-068, B03-069, B03-077 |

Niet voor de clients: ADR-0016 (één plugin met modules), ADR-0017 (analysewerker), ADR-0018 (planner en GPU-budget; wel:
"alle GPU's vol → gedrag van standaard Jellyfin, nooit weigeren", zie ADR-0024), ADR-0020 (opslag en gegevensbescherming
op de server; de HARDE EIS over kijkgeschiedenis geldt wel voor elke clienttest) en ADR-0021 (MediaGuard-grens).
