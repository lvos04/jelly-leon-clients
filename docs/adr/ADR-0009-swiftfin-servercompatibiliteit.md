# ADR-0009 — Swiftfin 1.6.1 verwacht Jellyfin 12.0; Jelly Leon draait 10.11.11

- **Status:** Vastgelegd (P0, 2026-11-09); **open gebruikersbesluit**; in P0 niets gewijzigd
- **Context (gemeten in de broncode):** Swiftfin 1.6.1 pint `jellyfin-sdk-swift` **3.0.0** (`Package.resolved`). Die SDK
  is gegenereerd tegen **Jellyfin API 12.0.0** (`Sources/Extensions/Info.swift`). Swiftfin noemt een server met
  major.minor lager dan de SDK-versie niet compatibel (`isVersionCompatible`) en toont dan
  *"Update to Jellyfin 12.0 for the best experience."* De Jelly Leon-server is gebaseerd op **Jellyfin 10.11.11**
  (`jelly-leon`). Swiftfin **1.5** gebruikte SDK **2.1.0** (API **10.11.8**). De Android-clients gebruiken
  jellyfin-sdk-kotlin 1.7.1 (API 10.10.7, minimum 10.10.0) en passen wel bij 10.11.11.

## Besluit voor P0

- De basislijn blijft **Swiftfin 1.6.1** (vastgelegd door de gebruiker). Niets gedowngraded of gepatcht.
- In de compatibiliteitsmatrix staat Swiftfin als *"waarschuwing; functionele compatibiliteit onbekend — NIET
  GEVALIDEERD (Mac/Xcode)"*, nooit als compatibel.

## Opties voor de gebruiker

| Optie | Voor | Tegen |
|---|---|---|
| A. Swiftfin 1.6.1 houden | nieuwste iOS/tvOS-app, upstream-sync actueel | waarschuwing in de app; API-verschillen 10.11 ↔ 12.0 kunnen functies breken; pas na echte test bekend |
| B. Swiftfin-basis naar **1.5** zetten tot de server naar 12.x gaat | SDK past bij 10.11 | ouder; tvOS/iOS-minimum en functies anders; sync-tool moet dan bewust een oudere tag accepteren (nu geweigerd) |
| C. `jelly-leon` naar Jellyfin 12.x | alle clients op één lijn | grote serverupgrade (jelly-leon meldt: v12.4 vraagt .NET 10, syncproef faalde terecht) |

Advies (niet uitgevoerd): eerst een echte test op een iPhone/Apple TV tegen een 10.11-testserver (D15, Mac/Xcode nodig);
daarna kiezen tussen A en B.
