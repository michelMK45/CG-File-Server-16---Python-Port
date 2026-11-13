"""Texts of the in-game CGFS16 menu in FIFA 16's languages (cgfs-ingame tools/menutexts.py; the CG Server 16
carries a byte-identical copy, server16_py/ingame_menu_texts.py). Standard library only.

FIFA 16 has 18 locales (data/loc, locale.ini AVAILABLE_LANG_n) in 16 languages; its ActionScript names them
with ION_Localization.GetLanguage(): eng fre ger ita spa (es, mx) por (pt, br) dut swe nor dan pol rus cze tur
ara chi. With USE_LANGUAGE_SELECT = 1 (locale.ini / RNA's rna.ini) the language is chosen in the game and can
change while it runs, so the menu translates itself when it opens:
  - the menu's data movie carries this table (table_string(), menudata.py);
  - the app writes keys instead of texts in the data: token("home", team="FC Barcelona") ->
    "{{home~team:FC Barcelona}}"; the menu replaces them in FIFA's language of the moment (English if a language
    has no text), and render() does the same in Python;
  - every record of the menu says its language (LANG), so the app compares what comes back in that language.
detect() is the app's guess when no record said it (logs): <game>/locale.ini or rna.ini DEFAULT_LANGUAGE, the
registry "Locale" of FIFA 16's installer, the app's own language, English.
"""
from __future__ import annotations

from pathlib import Path

LANGUAGES = ("eng", "spa", "fre", "ger", "ita", "por", "dut", "swe", "nor", "dan", "pol", "rus", "cze", "tur",
             "ara", "chi")
DEFAULT = "eng"
TWO_LETTER = {"en": "eng", "es": "spa", "fr": "fre", "de": "ger", "it": "ita", "pt": "por", "nl": "dut",
              "sv": "swe", "no": "nor", "nb": "nor", "da": "dan", "pl": "pol", "ru": "rus", "cs": "cze",
              "tr": "tur", "ar": "ara", "zh": "chi"}

TEXTS: dict[str, dict[str, str]] = {
    "eng": {
        "default": "Default (FIFA 16)", "not_yet": "Coming soon", "no_match": "Open it from the match hub (R3)",
        "none": "None (the stadium's own)", "random": "Picker/Random", "scope": "Assign to",
        "home": "Home team ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Default / Friendly",
        "round": "Round ({id})", "tour": "Tournament ({id})",
        "tab_stadium": "Stadium", "tab_scoreboard": "Scoreboard", "tab_tvlogo": "TV logo", "tab_movies": "Movies",
        "tab_kits": "Kits",
        "scoreboard_desc": "The scoreboard of that assignment. Default: removes the assignment.",
        "tvlogo_desc": "The TV logo of that assignment. Default: removes the assignment.",
        "scope_desc_pack": "Who it is assigned to, as in the overlay (F12): home team, derby, default / friendly, "
                           "round or tournament.",
        "scope_desc_stadium": "Who the stadiums are assigned to, as in the overlay (F12): home team, round or "
                              "tournament.",
        "scope_desc_movies": "Who the movies are assigned to, as in the overlay (F12): home team, derby, round or "
                             "tournament.",
        "stadium_open_hub": "Choose the stadium from the match hub, before the match (R3).",
        "no_stadiums": "There are no stadiums in StadiumGBD.",
        "stadium_desc": "The stadium added to the list when you save.",
        "add": "+ Add stadium", "add_desc": "Press A to choose a stadium and its assets and add it to the list.",
        "entry_desc": "Assigned. Press A to change its assets.",
        "save": "Save", "save_desc": "Press A to save it in the list. Back: return without saving.",
        "remove": "Remove", "remove_desc": "Press A to remove it from this assignment's list (its assets stay).",
        "match": "Match stadium",
        "match_desc": "Which one of the list is used in every match of this assignment (kept until you change it). Picker/Random: as usual, the overlay's picker "
                      "or a random one, depending on the app's setting.",
        "police": "Police", "police_desc": "Police level of the stadium (1-10).",
        "pitch": "Pitch pattern", "pitch_desc": "Pitch mowing pattern (FSW/PitchMowPattern).",
        "net": "Net colour", "net_desc": "Colour of the goal nets (FSW/Nets).",
        "goalpost": "Goalposts: model", "goalpost_desc": "Goalpost model (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Goalposts: texture", "goalposttex_desc": "Goalpost texture (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Net mesh", "netmesh_desc": "Net mesh (FSW/NetMesh).",
        "entrancecam": "Entrance camera",
        "entrancecam_desc": "Camera of the teams' walk-out (FSW/Camera/EntranceScene).",
        "movies_desc": "The intro and outro movies (MoviesGBD) of that assignment; the preview plays without sound. "
                       "Default: removes the assignment.",
        "movies_open_hub": "Choose the movies from the match hub, before the match (R3).",
        "kits_desc": "Kits will come in a future version.",
        "info": "App data ({source}, {stamp})",
        "behind": " · your last save has not reached the app yet",
        "no_data": "No app data: sample values. Open CG Server 16 and come back.",
    },
    "spa": {
        "default": "Por defecto (FIFA 16)", "not_yet": "Próximamente", "no_match": "Ábrelo desde el matchHub (R3)",
        "none": "Ninguno (el del estadio)", "random": "Selector/Al azar", "scope": "Asignar a",
        "home": "Equipo local ({team})", "derby": "Derbi ({home} - {away})", "default_scope": "Por defecto / Amistoso",
        "round": "Ronda ({id})", "tour": "Torneo ({id})",
        "tab_stadium": "Estadio", "tab_scoreboard": "Marcador", "tab_tvlogo": "Logo TV", "tab_movies": "Vídeos",
        "tab_kits": "Equipaciones",
        "scoreboard_desc": "El marcador de esa asignación. Por defecto: quita la asignación.",
        "tvlogo_desc": "El logo de TV de esa asignación. Por defecto: quita la asignación.",
        "scope_desc_pack": "A quién se asigna, como en el overlay (F12): equipo local, derbi, por defecto / amistoso, "
                           "ronda o torneo.",
        "scope_desc_stadium": "A quién se asignan los estadios, como en el overlay (F12): equipo local, ronda o "
                              "torneo.",
        "scope_desc_movies": "A quién se asignan los vídeos, como en el overlay (F12): equipo local, derbi, ronda o "
                             "torneo.",
        "stadium_open_hub": "Elige el estadio desde el matchHub, antes del partido (R3).",
        "no_stadiums": "No hay estadios en StadiumGBD.",
        "stadium_desc": "El estadio que se añade a la lista al guardar.",
        "add": "+ Agregar estadio", "add_desc": "Pulsa A para elegir un estadio y sus assets y añadirlo a la lista.",
        "entry_desc": "Asignado. Pulsa A para cambiar sus assets.",
        "save": "Guardar", "save_desc": "Pulsa A para guardarlo en la lista. Atrás: volver sin guardar.",
        "remove": "Quitar", "remove_desc": "Pulsa A para quitarlo de la lista de esta asignación (sus assets se quedan).",
        "match": "Estadio del partido",
        "match_desc": "Cuál de la lista se usa en todos los partidos de esta asignación (se guarda hasta que lo cambies). Selector/Al azar: como siempre, el selector del "
                      "overlay o uno al azar según el ajuste de la app.",
        "police": "Policía", "police_desc": "Nivel de policía del estadio (1-10).",
        "pitch": "Patrón del césped", "pitch_desc": "Dibujo del corte del césped (FSW/PitchMowPattern).",
        "net": "Color de la red", "net_desc": "Color de la red de las porterías (FSW/Nets).",
        "goalpost": "Portería: modelo", "goalpost_desc": "Modelo de portería (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Portería: textura", "goalposttex_desc": "Textura de la portería (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Malla de la red", "netmesh_desc": "Malla de la red (FSW/NetMesh).",
        "entrancecam": "Cámara de entrada",
        "entrancecam_desc": "Cámara de la salida de los equipos (FSW/Camera/EntranceScene).",
        "movies_desc": "Las entradas y salidas de vídeo (MoviesGBD) de esa asignación; la vista previa se reproduce "
                       "sin sonido. Por defecto: quita la asignación.",
        "movies_open_hub": "Elige los vídeos desde el matchHub, antes del partido (R3).",
        "kits_desc": "Las equipaciones llegarán en una próxima versión.",
        "info": "Datos de la app ({source}, {stamp})",
        "behind": " · tu último guardado aún no ha llegado a la app",
        "no_data": "Sin datos de la app: valores de ejemplo. Abre el CG Server 16 y vuelve a entrar.",
    },
    "fre": {
        "default": "Par défaut (FIFA 16)", "not_yet": "Bientôt", "no_match": "Ouvrez-le depuis le hub du match (R3)",
        "none": "Aucun (celui du stade)", "random": "Sélecteur/Aléatoire", "scope": "Attribuer à",
        "home": "Équipe à domicile ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Par défaut / Amical",
        "round": "Tour ({id})", "tour": "Tournoi ({id})",
        "tab_stadium": "Stade", "tab_scoreboard": "Tableau de score", "tab_tvlogo": "Logo TV", "tab_movies": "Vidéos",
        "tab_kits": "Maillots",
        "scoreboard_desc": "Le tableau de score de cette attribution. Par défaut : supprime l'attribution.",
        "tvlogo_desc": "Le logo TV de cette attribution. Par défaut : supprime l'attribution.",
        "scope_desc_pack": "À qui il est attribué, comme dans l'overlay (F12) : équipe à domicile, derby, par défaut / "
                           "amical, tour ou tournoi.",
        "scope_desc_stadium": "À qui les stades sont attribués, comme dans l'overlay (F12) : équipe à domicile, tour "
                              "ou tournoi.",
        "scope_desc_movies": "À qui les vidéos sont attribuées, comme dans l'overlay (F12) : équipe à domicile, derby, "
                             "tour ou tournoi.",
        "stadium_open_hub": "Choisissez le stade depuis le hub du match, avant le match (R3).",
        "no_stadiums": "Il n'y a aucun stade dans StadiumGBD.",
        "stadium_desc": "Le stade ajouté à la liste en enregistrant.",
        "add": "+ Ajouter un stade", "add_desc": "Appuyez sur A pour choisir un stade et ses assets et l'ajouter à la liste.",
        "entry_desc": "Attribué. Appuyez sur A pour changer ses assets.",
        "save": "Enregistrer", "save_desc": "Appuyez sur A pour l'enregistrer dans la liste. Retour : revenir sans enregistrer.",
        "remove": "Retirer", "remove_desc": "Appuyez sur A pour le retirer de la liste de cette attribution (ses assets restent).",
        "match": "Stade du match",
        "match_desc": "Lequel de la liste est utilisé pour tous les matchs de cette attribution (conservé jusqu'à ce que vous le changiez). Sélecteur/Aléatoire : comme d'habitude, le "
                      "sélecteur de l'overlay ou un stade au hasard selon le réglage de l'app.",
        "police": "Police", "police_desc": "Niveau de police du stade (1-10).",
        "pitch": "Motif de la pelouse", "pitch_desc": "Motif de tonte de la pelouse (FSW/PitchMowPattern).",
        "net": "Couleur des filets", "net_desc": "Couleur des filets des buts (FSW/Nets).",
        "goalpost": "Buts : modèle", "goalpost_desc": "Modèle des buts (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Buts : texture", "goalposttex_desc": "Texture des buts (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Maillage du filet", "netmesh_desc": "Maillage du filet (FSW/NetMesh).",
        "entrancecam": "Caméra d'entrée",
        "entrancecam_desc": "Caméra de l'entrée des équipes (FSW/Camera/EntranceScene).",
        "movies_desc": "Les vidéos d'entrée et de sortie (MoviesGBD) de cette attribution ; l'aperçu est joué sans "
                       "son. Par défaut : supprime l'attribution.",
        "movies_open_hub": "Choisissez les vidéos depuis le hub du match, avant le match (R3).",
        "kits_desc": "Les maillots arriveront dans une prochaine version.",
        "info": "Données de l'app ({source}, {stamp})",
        "behind": " · votre dernier enregistrement n'est pas encore arrivé à l'app",
        "no_data": "Pas de données de l'app : valeurs d'exemple. Ouvrez CG Server 16 et revenez.",
    },
    "ger": {
        "default": "Standard (FIFA 16)", "not_yet": "Demnächst", "no_match": "Im Spiel-Hub öffnen (R3)",
        "none": "Keins (das des Stadions)", "random": "Auswahl/Zufällig", "scope": "Zuweisen an",
        "home": "Heimteam ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Standard / Freundschaftsspiel",
        "round": "Runde ({id})", "tour": "Turnier ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Anzeigetafel", "tab_tvlogo": "TV-Logo", "tab_movies": "Videos",
        "tab_kits": "Trikots",
        "scoreboard_desc": "Die Anzeigetafel dieser Zuweisung. Standard: entfernt die Zuweisung.",
        "tvlogo_desc": "Das TV-Logo dieser Zuweisung. Standard: entfernt die Zuweisung.",
        "scope_desc_pack": "Wem es zugewiesen wird, wie im Overlay (F12): Heimteam, Derby, Standard / "
                           "Freundschaftsspiel, Runde oder Turnier.",
        "scope_desc_stadium": "Wem die Stadien zugewiesen werden, wie im Overlay (F12): Heimteam, Runde oder Turnier.",
        "scope_desc_movies": "Wem die Videos zugewiesen werden, wie im Overlay (F12): Heimteam, Derby, Runde oder "
                             "Turnier.",
        "stadium_open_hub": "Wähle das Stadion im Spiel-Hub vor dem Spiel (R3).",
        "no_stadiums": "In StadiumGBD gibt es keine Stadien.",
        "stadium_desc": "Das Stadion, das beim Speichern zur Liste hinzugefügt wird.",
        "add": "+ Stadion hinzufügen",
        "add_desc": "Drücke A, um ein Stadion und seine Assets zu wählen und es zur Liste hinzuzufügen.",
        "entry_desc": "Zugewiesen. Drücke A, um seine Assets zu ändern.",
        "save": "Speichern", "save_desc": "Drücke A, um es in der Liste zu speichern. Zurück: ohne Speichern zurück.",
        "remove": "Entfernen",
        "remove_desc": "Drücke A, um es aus der Liste dieser Zuweisung zu entfernen (seine Assets bleiben).",
        "match": "Stadion des Spiels",
        "match_desc": "Welches der Liste in allen Spielen dieser Zuweisung verwendet wird (bleibt gespeichert, bis du es änderst). Auswahl/Zufällig: wie immer, die Auswahl "
                      "des Overlays oder ein zufälliges, je nach Einstellung der App.",
        "police": "Polizei", "police_desc": "Polizeistufe des Stadions (1-10).",
        "pitch": "Rasenmuster", "pitch_desc": "Mähmuster des Rasens (FSW/PitchMowPattern).",
        "net": "Netzfarbe", "net_desc": "Farbe der Tornetze (FSW/Nets).",
        "goalpost": "Tor: Modell", "goalpost_desc": "Tormodell (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Tor: Textur", "goalposttex_desc": "Tortextur (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Netzgeflecht", "netmesh_desc": "Netzgeflecht (FSW/NetMesh).",
        "entrancecam": "Einlaufkamera", "entrancecam_desc": "Kamera beim Einlauf der Teams (FSW/Camera/EntranceScene).",
        "movies_desc": "Die Intro- und Outro-Videos (MoviesGBD) dieser Zuweisung; die Vorschau läuft ohne Ton. "
                       "Standard: entfernt die Zuweisung.",
        "movies_open_hub": "Wähle die Videos im Spiel-Hub vor dem Spiel (R3).",
        "kits_desc": "Trikots kommen in einer künftigen Version.",
        "info": "Daten der App ({source}, {stamp})",
        "behind": " · deine letzte Speicherung ist noch nicht bei der App angekommen",
        "no_data": "Keine Daten der App: Beispielwerte. Öffne CG Server 16 und komm zurück.",
    },
    "ita": {
        "default": "Predefinito (FIFA 16)", "not_yet": "Prossimamente", "no_match": "Aprilo dall'hub della partita (R3)",
        "none": "Nessuno (quello dello stadio)", "random": "Selettore/Casuale", "scope": "Assegna a",
        "home": "Squadra di casa ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Predefinito / Amichevole",
        "round": "Turno ({id})", "tour": "Torneo ({id})",
        "tab_stadium": "Stadio", "tab_scoreboard": "Tabellone", "tab_tvlogo": "Logo TV", "tab_movies": "Video",
        "tab_kits": "Divise",
        "scoreboard_desc": "Il tabellone di questa assegnazione. Predefinito: rimuove l'assegnazione.",
        "tvlogo_desc": "Il logo TV di questa assegnazione. Predefinito: rimuove l'assegnazione.",
        "scope_desc_pack": "A chi viene assegnato, come nell'overlay (F12): squadra di casa, derby, predefinito / "
                           "amichevole, turno o torneo.",
        "scope_desc_stadium": "A chi vengono assegnati gli stadi, come nell'overlay (F12): squadra di casa, turno o "
                              "torneo.",
        "scope_desc_movies": "A chi vengono assegnati i video, come nell'overlay (F12): squadra di casa, derby, turno "
                             "o torneo.",
        "stadium_open_hub": "Scegli lo stadio dall'hub della partita, prima della partita (R3).",
        "no_stadiums": "Non ci sono stadi in StadiumGBD.",
        "stadium_desc": "Lo stadio che viene aggiunto alla lista al salvataggio.",
        "add": "+ Aggiungi stadio", "add_desc": "Premi A per scegliere uno stadio e i suoi asset e aggiungerlo alla lista.",
        "entry_desc": "Assegnato. Premi A per cambiare i suoi asset.",
        "save": "Salva", "save_desc": "Premi A per salvarlo nella lista. Indietro: torna senza salvare.",
        "remove": "Rimuovi",
        "remove_desc": "Premi A per rimuoverlo dalla lista di questa assegnazione (i suoi asset restano).",
        "match": "Stadio della partita",
        "match_desc": "Quale della lista si usa in tutte le partite di questa assegnazione (resta salvato finché non lo cambi). Selettore/Casuale: come sempre, il selettore "
                      "dell'overlay o uno a caso secondo l'impostazione dell'app.",
        "police": "Polizia", "police_desc": "Livello di polizia dello stadio (1-10).",
        "pitch": "Motivo del prato", "pitch_desc": "Motivo di taglio del prato (FSW/PitchMowPattern).",
        "net": "Colore della rete", "net_desc": "Colore delle reti delle porte (FSW/Nets).",
        "goalpost": "Porta: modello", "goalpost_desc": "Modello della porta (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Porta: texture", "goalposttex_desc": "Texture della porta (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Maglia della rete", "netmesh_desc": "Maglia della rete (FSW/NetMesh).",
        "entrancecam": "Telecamera d'ingresso",
        "entrancecam_desc": "Telecamera dell'ingresso delle squadre (FSW/Camera/EntranceScene).",
        "movies_desc": "I video di ingresso e uscita (MoviesGBD) di questa assegnazione; l'anteprima è senza audio. "
                       "Predefinito: rimuove l'assegnazione.",
        "movies_open_hub": "Scegli i video dall'hub della partita, prima della partita (R3).",
        "kits_desc": "Le divise arriveranno in una prossima versione.",
        "info": "Dati dell'app ({source}, {stamp})",
        "behind": " · il tuo ultimo salvataggio non è ancora arrivato all'app",
        "no_data": "Nessun dato dall'app: valori di esempio. Apri CG Server 16 e rientra.",
    },
    "por": {
        "default": "Padrão (FIFA 16)", "not_yet": "Em breve", "no_match": "Abra-o no hub da partida (R3)",
        "none": "Nenhum (o do estádio)", "random": "Seletor/Aleatório", "scope": "Atribuir a",
        "home": "Equipa da casa ({team})", "derby": "Dérbi ({home} - {away})", "default_scope": "Padrão / Amigável",
        "round": "Ronda ({id})", "tour": "Torneio ({id})",
        "tab_stadium": "Estádio", "tab_scoreboard": "Placar", "tab_tvlogo": "Logo TV", "tab_movies": "Vídeos",
        "tab_kits": "Equipamentos",
        "scoreboard_desc": "O placar dessa atribuição. Padrão: remove a atribuição.",
        "tvlogo_desc": "O logo de TV dessa atribuição. Padrão: remove a atribuição.",
        "scope_desc_pack": "A quem é atribuído, como no overlay (F12): equipa da casa, dérbi, padrão / amigável, "
                           "ronda ou torneio.",
        "scope_desc_stadium": "A quem os estádios são atribuídos, como no overlay (F12): equipa da casa, ronda ou "
                              "torneio.",
        "scope_desc_movies": "A quem os vídeos são atribuídos, como no overlay (F12): equipa da casa, dérbi, ronda ou "
                             "torneio.",
        "stadium_open_hub": "Escolha o estádio no hub da partida, antes do jogo (R3).",
        "no_stadiums": "Não há estádios em StadiumGBD.",
        "stadium_desc": "O estádio que é adicionado à lista ao guardar.",
        "add": "+ Adicionar estádio",
        "add_desc": "Prima A para escolher um estádio e os seus assets e adicioná-lo à lista.",
        "entry_desc": "Atribuído. Prima A para mudar os seus assets.",
        "save": "Guardar", "save_desc": "Prima A para guardá-lo na lista. Voltar: voltar sem guardar.",
        "remove": "Remover",
        "remove_desc": "Prima A para removê-lo da lista desta atribuição (os seus assets ficam).",
        "match": "Estádio da partida",
        "match_desc": "Qual da lista é usado em todas as partidas desta atribuição (fica guardado até o mudar). Seletor/Aleatório: como sempre, o seletor do overlay "
                      "ou um aleatório conforme a definição da app.",
        "police": "Polícia", "police_desc": "Nível de polícia do estádio (1-10).",
        "pitch": "Padrão do relvado", "pitch_desc": "Padrão de corte do relvado (FSW/PitchMowPattern).",
        "net": "Cor da rede", "net_desc": "Cor das redes das balizas (FSW/Nets).",
        "goalpost": "Baliza: modelo", "goalpost_desc": "Modelo da baliza (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Baliza: textura", "goalposttex_desc": "Textura da baliza (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Malha da rede", "netmesh_desc": "Malha da rede (FSW/NetMesh).",
        "entrancecam": "Câmara de entrada",
        "entrancecam_desc": "Câmara da entrada das equipas (FSW/Camera/EntranceScene).",
        "movies_desc": "Os vídeos de entrada e saída (MoviesGBD) dessa atribuição; a pré-visualização é sem som. "
                       "Padrão: remove a atribuição.",
        "movies_open_hub": "Escolha os vídeos no hub da partida, antes do jogo (R3).",
        "kits_desc": "Os equipamentos chegarão numa próxima versão.",
        "info": "Dados da app ({source}, {stamp})",
        "behind": " · o seu último guardado ainda não chegou à app",
        "no_data": "Sem dados da app: valores de exemplo. Abra o CG Server 16 e volte a entrar.",
    },
    "dut": {
        "default": "Standaard (FIFA 16)", "not_yet": "Binnenkort", "no_match": "Open het vanuit de wedstrijdhub (R3)",
        "none": "Geen (die van het stadion)", "random": "Kiezer/Willekeurig", "scope": "Toewijzen aan",
        "home": "Thuisploeg ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Standaard / Vriendschappelijk",
        "round": "Ronde ({id})", "tour": "Toernooi ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Scorebord", "tab_tvlogo": "Tv-logo", "tab_movies": "Video's",
        "tab_kits": "Tenues",
        "scoreboard_desc": "Het scorebord van die toewijzing. Standaard: verwijdert de toewijzing.",
        "tvlogo_desc": "Het tv-logo van die toewijzing. Standaard: verwijdert de toewijzing.",
        "scope_desc_pack": "Aan wie het wordt toegewezen, zoals in de overlay (F12): thuisploeg, derby, standaard / "
                           "vriendschappelijk, ronde of toernooi.",
        "scope_desc_stadium": "Aan wie de stadions worden toegewezen, zoals in de overlay (F12): thuisploeg, ronde of "
                              "toernooi.",
        "scope_desc_movies": "Aan wie de video's worden toegewezen, zoals in de overlay (F12): thuisploeg, derby, ronde "
                             "of toernooi.",
        "stadium_open_hub": "Kies het stadion in de wedstrijdhub, voor de wedstrijd (R3).",
        "no_stadiums": "Er staan geen stadions in StadiumGBD.",
        "stadium_desc": "Het stadion dat bij het opslaan aan de lijst wordt toegevoegd.",
        "add": "+ Stadion toevoegen",
        "add_desc": "Druk op A om een stadion en zijn assets te kiezen en het aan de lijst toe te voegen.",
        "entry_desc": "Toegewezen. Druk op A om zijn assets te wijzigen.",
        "save": "Opslaan", "save_desc": "Druk op A om het in de lijst op te slaan. Terug: terug zonder opslaan.",
        "remove": "Verwijderen",
        "remove_desc": "Druk op A om het uit de lijst van deze toewijzing te halen (zijn assets blijven).",
        "match": "Stadion van de wedstrijd",
        "match_desc": "Welke van de lijst in alle wedstrijden van deze toewijzing wordt gebruikt (blijft bewaard tot je het wijzigt). Kiezer/Willekeurig: zoals altijd, de "
                      "kiezer van de overlay of een willekeurige, afhankelijk van de instelling van de app.",
        "police": "Politie", "police_desc": "Politieniveau van het stadion (1-10).",
        "pitch": "Grasmotief", "pitch_desc": "Maaipatroon van het veld (FSW/PitchMowPattern).",
        "net": "Netkleur", "net_desc": "Kleur van de doelnetten (FSW/Nets).",
        "goalpost": "Doel: model", "goalpost_desc": "Doelmodel (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Doel: textuur", "goalposttex_desc": "Doeltextuur (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Netmaas", "netmesh_desc": "Netmaas (FSW/NetMesh).",
        "entrancecam": "Opkomstcamera", "entrancecam_desc": "Camera bij de opkomst van de teams (FSW/Camera/EntranceScene).",
        "movies_desc": "De intro- en outrovideo's (MoviesGBD) van die toewijzing; de voorvertoning speelt zonder "
                       "geluid. Standaard: verwijdert de toewijzing.",
        "movies_open_hub": "Kies de video's in de wedstrijdhub, voor de wedstrijd (R3).",
        "kits_desc": "Tenues komen in een volgende versie.",
        "info": "Gegevens van de app ({source}, {stamp})",
        "behind": " · je laatste opslag is nog niet bij de app aangekomen",
        "no_data": "Geen gegevens van de app: voorbeeldwaarden. Open CG Server 16 en kom terug.",
    },
    "swe": {
        "default": "Standard (FIFA 16)", "not_yet": "Kommer snart", "no_match": "Öppna den från matchhubben (R3)",
        "none": "Ingen (arenans egen)", "random": "Väljare/Slumpmässig", "scope": "Tilldela till",
        "home": "Hemmalag ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Standard / Vänskapsmatch",
        "round": "Omgång ({id})", "tour": "Turnering ({id})",
        "tab_stadium": "Arena", "tab_scoreboard": "Resultattavla", "tab_tvlogo": "TV-logga", "tab_movies": "Videor",
        "tab_kits": "Matchställ",
        "scoreboard_desc": "Den tilldelningens resultattavla. Standard: tar bort tilldelningen.",
        "tvlogo_desc": "Den tilldelningens TV-logga. Standard: tar bort tilldelningen.",
        "scope_desc_pack": "Vem den tilldelas, som i overlayen (F12): hemmalag, derby, standard / vänskapsmatch, "
                           "omgång eller turnering.",
        "scope_desc_stadium": "Vem arenorna tilldelas, som i overlayen (F12): hemmalag, omgång eller turnering.",
        "scope_desc_movies": "Vem videorna tilldelas, som i overlayen (F12): hemmalag, derby, omgång eller turnering.",
        "stadium_open_hub": "Välj arenan i matchhubben före matchen (R3).",
        "no_stadiums": "Det finns inga arenor i StadiumGBD.",
        "stadium_desc": "Arenan som läggs till i listan när du sparar.",
        "add": "+ Lägg till arena", "add_desc": "Tryck A för att välja en arena och dess assets och lägga till den i listan.",
        "entry_desc": "Tilldelad. Tryck A för att ändra dess assets.",
        "save": "Spara", "save_desc": "Tryck A för att spara den i listan. Tillbaka: gå tillbaka utan att spara.",
        "remove": "Ta bort", "remove_desc": "Tryck A för att ta bort den från tilldelningens lista (dess assets finns kvar).",
        "match": "Matchens arena",
        "match_desc": "Vilken i listan som används i alla matcher för tilldelningen (sparas tills du ändrar det). Väljare/Slumpmässig: som vanligt, overlayens "
                      "väljare eller en slumpmässig beroende på appens inställning.",
        "police": "Polis", "police_desc": "Arenans polisnivå (1-10).",
        "pitch": "Gräsmönster", "pitch_desc": "Klippmönster på planen (FSW/PitchMowPattern).",
        "net": "Nätfärg", "net_desc": "Färg på målnäten (FSW/Nets).",
        "goalpost": "Mål: modell", "goalpost_desc": "Målmodell (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Mål: textur", "goalposttex_desc": "Måltextur (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Nätmaska", "netmesh_desc": "Nätmaska (FSW/NetMesh).",
        "entrancecam": "Inmarschkamera", "entrancecam_desc": "Kamera för lagens inmarsch (FSW/Camera/EntranceScene).",
        "movies_desc": "Tilldelningens intro- och outrovideor (MoviesGBD); förhandsvisningen spelas utan ljud. "
                       "Standard: tar bort tilldelningen.",
        "movies_open_hub": "Välj videorna i matchhubben före matchen (R3).",
        "kits_desc": "Matchställ kommer i en framtida version.",
        "info": "Appens data ({source}, {stamp})",
        "behind": " · din senaste sparning har inte nått appen än",
        "no_data": "Inga data från appen: exempelvärden. Öppna CG Server 16 och kom tillbaka.",
    },
    "nor": {
        "default": "Standard (FIFA 16)", "not_yet": "Kommer snart", "no_match": "Åpne den fra kamphuben (R3)",
        "none": "Ingen (stadionets egen)", "random": "Velger/Tilfeldig", "scope": "Tildel til",
        "home": "Hjemmelag ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Standard / Vennskapskamp",
        "round": "Runde ({id})", "tour": "Turnering ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Resultattavle", "tab_tvlogo": "TV-logo", "tab_movies": "Videoer",
        "tab_kits": "Drakter",
        "scoreboard_desc": "Resultattavlen for den tildelingen. Standard: fjerner tildelingen.",
        "tvlogo_desc": "TV-logoen for den tildelingen. Standard: fjerner tildelingen.",
        "scope_desc_pack": "Hvem den tildeles, som i overlayet (F12): hjemmelag, derby, standard / vennskapskamp, "
                           "runde eller turnering.",
        "scope_desc_stadium": "Hvem stadionene tildeles, som i overlayet (F12): hjemmelag, runde eller turnering.",
        "scope_desc_movies": "Hvem videoene tildeles, som i overlayet (F12): hjemmelag, derby, runde eller turnering.",
        "stadium_open_hub": "Velg stadion fra kamphuben før kampen (R3).",
        "no_stadiums": "Det finnes ingen stadioner i StadiumGBD.",
        "stadium_desc": "Stadionet som legges til i listen når du lagrer.",
        "add": "+ Legg til stadion", "add_desc": "Trykk A for å velge et stadion og dets assets og legge det til i listen.",
        "entry_desc": "Tildelt. Trykk A for å endre dets assets.",
        "save": "Lagre", "save_desc": "Trykk A for å lagre det i listen. Tilbake: gå tilbake uten å lagre.",
        "remove": "Fjern", "remove_desc": "Trykk A for å fjerne det fra tildelingens liste (dets assets blir værende).",
        "match": "Kampens stadion",
        "match_desc": "Hvilket i listen som brukes i alle kamper for tildelingen (lagres til du endrer det). Velger/Tilfeldig: som vanlig, overlayets velger "
                      "eller et tilfeldig avhengig av appens innstilling.",
        "police": "Politi", "police_desc": "Stadionets politinivå (1-10).",
        "pitch": "Gressmønster", "pitch_desc": "Klippemønster på banen (FSW/PitchMowPattern).",
        "net": "Nettfarge", "net_desc": "Farge på målnettene (FSW/Nets).",
        "goalpost": "Mål: modell", "goalpost_desc": "Målmodell (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Mål: tekstur", "goalposttex_desc": "Måltekstur (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Nettmaske", "netmesh_desc": "Nettmaske (FSW/NetMesh).",
        "entrancecam": "Inngangskamera", "entrancecam_desc": "Kamera for lagenes inngang (FSW/Camera/EntranceScene).",
        "movies_desc": "Tildelingens intro- og outrovideoer (MoviesGBD); forhåndsvisningen spilles uten lyd. "
                       "Standard: fjerner tildelingen.",
        "movies_open_hub": "Velg videoene fra kamphuben før kampen (R3).",
        "kits_desc": "Drakter kommer i en fremtidig versjon.",
        "info": "Appens data ({source}, {stamp})",
        "behind": " · din siste lagring har ikke nådd appen ennå",
        "no_data": "Ingen data fra appen: eksempelverdier. Åpne CG Server 16 og kom tilbake.",
    },
    "dan": {
        "default": "Standard (FIFA 16)", "not_yet": "Kommer snart", "no_match": "Åbn den fra kamphubben (R3)",
        "none": "Ingen (stadionets egen)", "random": "Vælger/Tilfældig", "scope": "Tildel til",
        "home": "Hjemmehold ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Standard / Venskabskamp",
        "round": "Runde ({id})", "tour": "Turnering ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Resultattavle", "tab_tvlogo": "TV-logo", "tab_movies": "Videoer",
        "tab_kits": "Spilletøj",
        "scoreboard_desc": "Den tildelings resultattavle. Standard: fjerner tildelingen.",
        "tvlogo_desc": "Den tildelings TV-logo. Standard: fjerner tildelingen.",
        "scope_desc_pack": "Hvem den tildeles, som i overlayet (F12): hjemmehold, derby, standard / venskabskamp, "
                           "runde eller turnering.",
        "scope_desc_stadium": "Hvem stadionerne tildeles, som i overlayet (F12): hjemmehold, runde eller turnering.",
        "scope_desc_movies": "Hvem videoerne tildeles, som i overlayet (F12): hjemmehold, derby, runde eller turnering.",
        "stadium_open_hub": "Vælg stadion fra kamphubben før kampen (R3).",
        "no_stadiums": "Der er ingen stadioner i StadiumGBD.",
        "stadium_desc": "Stadionet, der føjes til listen, når du gemmer.",
        "add": "+ Tilføj stadion", "add_desc": "Tryk A for at vælge et stadion og dets assets og føje det til listen.",
        "entry_desc": "Tildelt. Tryk A for at ændre dets assets.",
        "save": "Gem", "save_desc": "Tryk A for at gemme det i listen. Tilbage: gå tilbage uden at gemme.",
        "remove": "Fjern", "remove_desc": "Tryk A for at fjerne det fra tildelingens liste (dets assets bliver).",
        "match": "Kampens stadion",
        "match_desc": "Hvilket på listen der bruges i alle kampe for tildelingen (gemmes, indtil du ændrer det). Vælger/Tilfældig: som altid, overlayets vælger "
                      "eller et tilfældigt afhængigt af appens indstilling.",
        "police": "Politi", "police_desc": "Stadionets politiniveau (1-10).",
        "pitch": "Græsmønster", "pitch_desc": "Klippemønster på banen (FSW/PitchMowPattern).",
        "net": "Netfarve", "net_desc": "Farve på målnettene (FSW/Nets).",
        "goalpost": "Mål: model", "goalpost_desc": "Målmodel (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Mål: tekstur", "goalposttex_desc": "Måltekstur (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Netmaske", "netmesh_desc": "Netmaske (FSW/NetMesh).",
        "entrancecam": "Indgangskamera", "entrancecam_desc": "Kamera ved holdenes indgang (FSW/Camera/EntranceScene).",
        "movies_desc": "Tildelingens intro- og outrovideoer (MoviesGBD); forhåndsvisningen afspilles uden lyd. "
                       "Standard: fjerner tildelingen.",
        "movies_open_hub": "Vælg videoerne fra kamphubben før kampen (R3).",
        "kits_desc": "Spilletøj kommer i en fremtidig version.",
        "info": "Appens data ({source}, {stamp})",
        "behind": " · din seneste gemning er endnu ikke nået frem til appen",
        "no_data": "Ingen data fra appen: eksempelværdier. Åbn CG Server 16 og kom tilbage.",
    },
    "pol": {
        "default": "Domyślny (FIFA 16)", "not_yet": "Wkrótce", "no_match": "Otwórz z centrum meczu (R3)",
        "none": "Brak (własny stadionu)", "random": "Wybór/Losowo", "scope": "Przypisz do",
        "home": "Gospodarze ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Domyślny / Towarzyski",
        "round": "Runda ({id})", "tour": "Turniej ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Tablica wyników", "tab_tvlogo": "Logo TV", "tab_movies": "Filmy",
        "tab_kits": "Stroje",
        "scoreboard_desc": "Tablica wyników tego przypisania. Domyślny: usuwa przypisanie.",
        "tvlogo_desc": "Logo TV tego przypisania. Domyślny: usuwa przypisanie.",
        "scope_desc_pack": "Komu jest przypisane, jak w overlayu (F12): gospodarze, derby, domyślny / towarzyski, "
                           "runda lub turniej.",
        "scope_desc_stadium": "Komu przypisane są stadiony, jak w overlayu (F12): gospodarze, runda lub turniej.",
        "scope_desc_movies": "Komu przypisane są filmy, jak w overlayu (F12): gospodarze, derby, runda lub turniej.",
        "stadium_open_hub": "Wybierz stadion w centrum meczu, przed meczem (R3).",
        "no_stadiums": "W StadiumGBD nie ma stadionów.",
        "stadium_desc": "Stadion dodawany do listy przy zapisie.",
        "add": "+ Dodaj stadion", "add_desc": "Naciśnij A, aby wybrać stadion i jego zasoby i dodać go do listy.",
        "entry_desc": "Przypisany. Naciśnij A, aby zmienić jego zasoby.",
        "save": "Zapisz", "save_desc": "Naciśnij A, aby zapisać go na liście. Wstecz: wróć bez zapisywania.",
        "remove": "Usuń", "remove_desc": "Naciśnij A, aby usunąć go z listy tego przypisania (jego zasoby zostają).",
        "match": "Stadion meczu",
        "match_desc": "Który z listy jest używany we wszystkich meczach tego przypisania (zapisany, dopóki go nie zmienisz). Wybór/Losowo: jak zawsze, wybór z overlayu lub "
                      "losowy, zależnie od ustawienia aplikacji.",
        "police": "Policja", "police_desc": "Poziom policji na stadionie (1-10).",
        "pitch": "Wzór murawy", "pitch_desc": "Wzór koszenia murawy (FSW/PitchMowPattern).",
        "net": "Kolor siatki", "net_desc": "Kolor siatek bramek (FSW/Nets).",
        "goalpost": "Bramka: model", "goalpost_desc": "Model bramki (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Bramka: tekstura", "goalposttex_desc": "Tekstura bramki (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Oczka siatki", "netmesh_desc": "Oczka siatki (FSW/NetMesh).",
        "entrancecam": "Kamera wejścia", "entrancecam_desc": "Kamera wyjścia drużyn (FSW/Camera/EntranceScene).",
        "movies_desc": "Filmy wejścia i wyjścia (MoviesGBD) tego przypisania; podgląd odtwarza się bez dźwięku. "
                       "Domyślny: usuwa przypisanie.",
        "movies_open_hub": "Wybierz filmy w centrum meczu, przed meczem (R3).",
        "kits_desc": "Stroje pojawią się w przyszłej wersji.",
        "info": "Dane aplikacji ({source}, {stamp})",
        "behind": " · twój ostatni zapis jeszcze nie dotarł do aplikacji",
        "no_data": "Brak danych z aplikacji: przykładowe wartości. Otwórz CG Server 16 i wróć.",
    },
    "rus": {
        "default": "По умолчанию (FIFA 16)", "not_yet": "Скоро", "no_match": "Откройте его из центра матча (R3)",
        "none": "Нет (стадиона)", "random": "Выбор/Случайно", "scope": "Назначить",
        "home": "Хозяева ({team})", "derby": "Дерби ({home} - {away})", "default_scope": "По умолчанию / Товарищеский",
        "round": "Раунд ({id})", "tour": "Турнир ({id})",
        "tab_stadium": "Стадион", "tab_scoreboard": "Табло", "tab_tvlogo": "Логотип ТВ", "tab_movies": "Видео",
        "tab_kits": "Форма",
        "scoreboard_desc": "Табло этого назначения. По умолчанию: удаляет назначение.",
        "tvlogo_desc": "Логотип ТВ этого назначения. По умолчанию: удаляет назначение.",
        "scope_desc_pack": "Кому назначается, как в оверлее (F12): хозяева, дерби, по умолчанию / товарищеский, раунд "
                           "или турнир.",
        "scope_desc_stadium": "Кому назначаются стадионы, как в оверлее (F12): хозяева, раунд или турнир.",
        "scope_desc_movies": "Кому назначаются видео, как в оверлее (F12): хозяева, дерби, раунд или турнир.",
        "stadium_open_hub": "Выберите стадион в центре матча перед игрой (R3).",
        "no_stadiums": "В StadiumGBD нет стадионов.",
        "stadium_desc": "Стадион, который добавляется в список при сохранении.",
        "add": "+ Добавить стадион", "add_desc": "Нажмите A, чтобы выбрать стадион и его ассеты и добавить его в список.",
        "entry_desc": "Назначен. Нажмите A, чтобы изменить его ассеты.",
        "save": "Сохранить", "save_desc": "Нажмите A, чтобы сохранить его в списке. Назад: вернуться без сохранения.",
        "remove": "Убрать", "remove_desc": "Нажмите A, чтобы убрать его из списка этого назначения (его ассеты остаются).",
        "match": "Стадион матча",
        "match_desc": "Какой из списка используется во всех матчах этого назначения (сохраняется, пока вы его не измените). Выбор/Случайно: как обычно, выбор в оверлее или "
                      "случайный, в зависимости от настройки приложения.",
        "police": "Полиция", "police_desc": "Уровень полиции на стадионе (1-10).",
        "pitch": "Узор газона", "pitch_desc": "Узор стрижки газона (FSW/PitchMowPattern).",
        "net": "Цвет сетки", "net_desc": "Цвет сеток ворот (FSW/Nets).",
        "goalpost": "Ворота: модель", "goalpost_desc": "Модель ворот (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Ворота: текстура", "goalposttex_desc": "Текстура ворот (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Ячейки сетки", "netmesh_desc": "Ячейки сетки (FSW/NetMesh).",
        "entrancecam": "Камера выхода", "entrancecam_desc": "Камера выхода команд (FSW/Camera/EntranceScene).",
        "movies_desc": "Вступительные и финальные видео (MoviesGBD) этого назначения; превью без звука. По умолчанию: "
                       "удаляет назначение.",
        "movies_open_hub": "Выберите видео в центре матча перед игрой (R3).",
        "kits_desc": "Форма появится в одной из следующих версий.",
        "info": "Данные приложения ({source}, {stamp})",
        "behind": " · ваше последнее сохранение ещё не дошло до приложения",
        "no_data": "Нет данных приложения: примерные значения. Откройте CG Server 16 и вернитесь.",
    },
    "cze": {
        "default": "Výchozí (FIFA 16)", "not_yet": "Již brzy", "no_match": "Otevřete ho z centra zápasu (R3)",
        "none": "Žádný (stadionu)", "random": "Výběr/Náhodně", "scope": "Přiřadit k",
        "home": "Domácí tým ({team})", "derby": "Derby ({home} - {away})", "default_scope": "Výchozí / Přátelský",
        "round": "Kolo ({id})", "tour": "Turnaj ({id})",
        "tab_stadium": "Stadion", "tab_scoreboard": "Výsledková tabule", "tab_tvlogo": "Logo TV", "tab_movies": "Videa",
        "tab_kits": "Dresy",
        "scoreboard_desc": "Výsledková tabule tohoto přiřazení. Výchozí: odstraní přiřazení.",
        "tvlogo_desc": "Logo TV tohoto přiřazení. Výchozí: odstraní přiřazení.",
        "scope_desc_pack": "Komu se přiřazuje, jako v overlayi (F12): domácí tým, derby, výchozí / přátelský, kolo "
                           "nebo turnaj.",
        "scope_desc_stadium": "Komu se přiřazují stadiony, jako v overlayi (F12): domácí tým, kolo nebo turnaj.",
        "scope_desc_movies": "Komu se přiřazují videa, jako v overlayi (F12): domácí tým, derby, kolo nebo turnaj.",
        "stadium_open_hub": "Vyberte stadion v centru zápasu před zápasem (R3).",
        "no_stadiums": "Ve StadiumGBD nejsou žádné stadiony.",
        "stadium_desc": "Stadion, který se při uložení přidá do seznamu.",
        "add": "+ Přidat stadion", "add_desc": "Stiskněte A pro výběr stadionu a jeho assetů a přidání do seznamu.",
        "entry_desc": "Přiřazeno. Stiskněte A pro změnu jeho assetů.",
        "save": "Uložit", "save_desc": "Stiskněte A pro uložení do seznamu. Zpět: vrátit se bez uložení.",
        "remove": "Odebrat", "remove_desc": "Stiskněte A pro odebrání ze seznamu tohoto přiřazení (jeho assety zůstanou).",
        "match": "Stadion zápasu",
        "match_desc": "Který ze seznamu se použije ve všech zápasech tohoto přiřazení (zůstane uložený, dokud ho nezměníte). Výběr/Náhodně: jako vždy, výběr v overlayi nebo "
                      "náhodný podle nastavení aplikace.",
        "police": "Policie", "police_desc": "Úroveň policie na stadionu (1-10).",
        "pitch": "Vzor trávníku", "pitch_desc": "Vzor sekání trávníku (FSW/PitchMowPattern).",
        "net": "Barva sítě", "net_desc": "Barva sítí branek (FSW/Nets).",
        "goalpost": "Branka: model", "goalpost_desc": "Model branky (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Branka: textura", "goalposttex_desc": "Textura branky (FSW/Goalpost/GoalpostColor).",
        "netmesh": "Oka sítě", "netmesh_desc": "Oka sítě (FSW/NetMesh).",
        "entrancecam": "Kamera nástupu", "entrancecam_desc": "Kamera nástupu týmů (FSW/Camera/EntranceScene).",
        "movies_desc": "Úvodní a závěrečná videa (MoviesGBD) tohoto přiřazení; náhled se přehrává bez zvuku. "
                       "Výchozí: odstraní přiřazení.",
        "movies_open_hub": "Vyberte videa v centru zápasu před zápasem (R3).",
        "kits_desc": "Dresy přijdou v příští verzi.",
        "info": "Data aplikace ({source}, {stamp})",
        "behind": " · vaše poslední uložení ještě nedorazilo do aplikace",
        "no_data": "Žádná data z aplikace: ukázkové hodnoty. Otevřete CG Server 16 a vraťte se.",
    },
    "tur": {
        "default": "Varsayılan (FIFA 16)", "not_yet": "Yakında", "no_match": "Maç merkezinden açın (R3)",
        "none": "Yok (stadyumun kendisi)", "random": "Seçici/Rastgele", "scope": "Ata",
        "home": "Ev sahibi ({team})", "derby": "Derbi ({home} - {away})", "default_scope": "Varsayılan / Hazırlık",
        "round": "Tur ({id})", "tour": "Turnuva ({id})",
        "tab_stadium": "Stadyum", "tab_scoreboard": "Skor tabelası", "tab_tvlogo": "TV logosu", "tab_movies": "Videolar",
        "tab_kits": "Formalar",
        "scoreboard_desc": "Bu atamanın skor tabelası. Varsayılan: atamayı kaldırır.",
        "tvlogo_desc": "Bu atamanın TV logosu. Varsayılan: atamayı kaldırır.",
        "scope_desc_pack": "Kime atandığı, overlay'deki gibi (F12): ev sahibi, derbi, varsayılan / hazırlık, tur veya "
                           "turnuva.",
        "scope_desc_stadium": "Stadyumların kime atandığı, overlay'deki gibi (F12): ev sahibi, tur veya turnuva.",
        "scope_desc_movies": "Videoların kime atandığı, overlay'deki gibi (F12): ev sahibi, derbi, tur veya turnuva.",
        "stadium_open_hub": "Stadyumu maçtan önce maç merkezinden seçin (R3).",
        "no_stadiums": "StadiumGBD içinde stadyum yok.",
        "stadium_desc": "Kaydedince listeye eklenen stadyum.",
        "add": "+ Stadyum ekle", "add_desc": "Bir stadyum ve varlıklarını seçip listeye eklemek için A'ya basın.",
        "entry_desc": "Atandı. Varlıklarını değiştirmek için A'ya basın.",
        "save": "Kaydet", "save_desc": "Listeye kaydetmek için A'ya basın. Geri: kaydetmeden dön.",
        "remove": "Kaldır", "remove_desc": "Bu atamanın listesinden kaldırmak için A'ya basın (varlıkları kalır).",
        "match": "Maçın stadyumu",
        "match_desc": "Listeden hangisinin bu atamanın tüm maçlarında kullanılacağı (siz değiştirene kadar kaydedilir). Seçici/Rastgele: her zamanki gibi, uygulamanın "
                      "ayarına göre overlay seçicisi veya rastgele biri.",
        "police": "Polis", "police_desc": "Stadyumun polis seviyesi (1-10).",
        "pitch": "Çim deseni", "pitch_desc": "Çim biçme deseni (FSW/PitchMowPattern).",
        "net": "File rengi", "net_desc": "Kale filelerinin rengi (FSW/Nets).",
        "goalpost": "Kale: model", "goalpost_desc": "Kale modeli (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "Kale: doku", "goalposttex_desc": "Kale dokusu (FSW/Goalpost/GoalpostColor).",
        "netmesh": "File örgüsü", "netmesh_desc": "File örgüsü (FSW/NetMesh).",
        "entrancecam": "Giriş kamerası", "entrancecam_desc": "Takımların sahaya çıkış kamerası (FSW/Camera/EntranceScene).",
        "movies_desc": "Bu atamanın giriş ve çıkış videoları (MoviesGBD); önizleme sessiz oynatılır. Varsayılan: "
                       "atamayı kaldırır.",
        "movies_open_hub": "Videoları maçtan önce maç merkezinden seçin (R3).",
        "kits_desc": "Formalar gelecek bir sürümde gelecek.",
        "info": "Uygulama verileri ({source}, {stamp})",
        "behind": " · son kaydınız henüz uygulamaya ulaşmadı",
        "no_data": "Uygulama verisi yok: örnek değerler. CG Server 16'yı açıp geri dönün.",
    },
    "ara": {
        "default": "افتراضي (FIFA 16)", "not_yet": "قريبًا", "no_match": "افتحه من مركز المباراة (R3)",
        "none": "لا شيء (الخاص بالملعب)", "random": "المحدد/عشوائي", "scope": "تعيين إلى",
        "home": "الفريق المضيف ({team})", "derby": "ديربي ({home} - {away})", "default_scope": "افتراضي / ودية",
        "round": "الجولة ({id})", "tour": "البطولة ({id})",
        "tab_stadium": "الملعب", "tab_scoreboard": "لوحة النتائج", "tab_tvlogo": "شعار التلفزيون", "tab_movies": "الفيديوهات",
        "tab_kits": "الأطقم",
        "scoreboard_desc": "لوحة النتائج لهذا التعيين. افتراضي: يزيل التعيين.",
        "tvlogo_desc": "شعار التلفزيون لهذا التعيين. افتراضي: يزيل التعيين.",
        "scope_desc_pack": "لمن يتم التعيين، كما في الواجهة (F12): الفريق المضيف، ديربي، افتراضي / ودية، الجولة أو "
                           "البطولة.",
        "scope_desc_stadium": "لمن يتم تعيين الملاعب، كما في الواجهة (F12): الفريق المضيف، الجولة أو البطولة.",
        "scope_desc_movies": "لمن يتم تعيين الفيديوهات، كما في الواجهة (F12): الفريق المضيف، ديربي، الجولة أو البطولة.",
        "stadium_open_hub": "اختر الملعب من مركز المباراة قبل المباراة (R3).",
        "no_stadiums": "لا توجد ملاعب في StadiumGBD.",
        "stadium_desc": "الملعب الذي يضاف إلى القائمة عند الحفظ.",
        "add": "+ إضافة ملعب", "add_desc": "اضغط A لاختيار ملعب وملحقاته وإضافته إلى القائمة.",
        "entry_desc": "معيّن. اضغط A لتغيير ملحقاته.",
        "save": "حفظ", "save_desc": "اضغط A لحفظه في القائمة. رجوع: العودة دون حفظ.",
        "remove": "إزالة", "remove_desc": "اضغط A لإزالته من قائمة هذا التعيين (تبقى ملحقاته).",
        "match": "ملعب المباراة",
        "match_desc": "أي ملعب من القائمة يستخدم في كل مباريات هذا التعيين (يبقى محفوظًا حتى تغيّره). المحدد/عشوائي: كالمعتاد، محدد الواجهة أو ملعب "
                      "عشوائي حسب إعداد التطبيق.",
        "police": "الشرطة", "police_desc": "مستوى الشرطة في الملعب (1-10).",
        "pitch": "نقشة العشب", "pitch_desc": "نمط قص العشب (FSW/PitchMowPattern).",
        "net": "لون الشباك", "net_desc": "لون شباك المرمى (FSW/Nets).",
        "goalpost": "المرمى: الطراز", "goalpost_desc": "طراز المرمى (FSW/Goalpost/GoalpostModel).",
        "goalposttex": "المرمى: الخامة", "goalposttex_desc": "خامة المرمى (FSW/Goalpost/GoalpostColor).",
        "netmesh": "عيون الشبكة", "netmesh_desc": "عيون الشبكة (FSW/NetMesh).",
        "entrancecam": "كاميرا الدخول", "entrancecam_desc": "كاميرا دخول الفريقين (FSW/Camera/EntranceScene).",
        "movies_desc": "فيديوهات الدخول والخروج (MoviesGBD) لهذا التعيين؛ تُعرض المعاينة دون صوت. افتراضي: يزيل التعيين.",
        "movies_open_hub": "اختر الفيديوهات من مركز المباراة قبل المباراة (R3).",
        "kits_desc": "ستأتي الأطقم في إصدار قادم.",
        "info": "بيانات التطبيق ({source}، {stamp})",
        "behind": " · آخر حفظ لك لم يصل إلى التطبيق بعد",
        "no_data": "لا توجد بيانات من التطبيق: قيم تجريبية. افتح CG Server 16 ثم عد.",
    },
    "chi": {
        "default": "預設 (FIFA 16)", "not_yet": "即將推出", "no_match": "請從比賽中心開啟 (R3)",
        "none": "無 (球場本身的)", "random": "選擇器/隨機", "scope": "指派給",
        "home": "主隊 ({team})", "derby": "打吡 ({home} - {away})", "default_scope": "預設 / 友誼賽",
        "round": "輪次 ({id})", "tour": "賽事 ({id})",
        "tab_stadium": "球場", "tab_scoreboard": "記分板", "tab_tvlogo": "電視台標誌", "tab_movies": "影片",
        "tab_kits": "球衣",
        "scoreboard_desc": "該指派的記分板。預設：移除指派。",
        "tvlogo_desc": "該指派的電視台標誌。預設：移除指派。",
        "scope_desc_pack": "指派給誰，與疊加介面 (F12) 相同：主隊、打吡、預設 / 友誼賽、輪次或賽事。",
        "scope_desc_stadium": "球場指派給誰，與疊加介面 (F12) 相同：主隊、輪次或賽事。",
        "scope_desc_movies": "影片指派給誰，與疊加介面 (F12) 相同：主隊、打吡、輪次或賽事。",
        "stadium_open_hub": "請在比賽前於比賽中心選擇球場 (R3)。",
        "no_stadiums": "StadiumGBD 中沒有球場。",
        "stadium_desc": "儲存時加入清單的球場。",
        "add": "+ 新增球場", "add_desc": "按 A 選擇球場及其資源並加入清單。",
        "entry_desc": "已指派。按 A 變更其資源。",
        "save": "儲存", "save_desc": "按 A 儲存至清單。返回：不儲存並返回。",
        "remove": "移除", "remove_desc": "按 A 將其從此指派的清單中移除 (其資源保留)。",
        "match": "比賽球場",
        "match_desc": "此指派的所有比賽使用清單中的哪一個 (會保存直到你更改)。選擇器/隨機：照常，依應用程式設定使用疊加介面的選擇器或隨機一個。",
        "police": "警察", "police_desc": "球場的警察等級 (1-10)。",
        "pitch": "草皮圖案", "pitch_desc": "草皮修剪圖案 (FSW/PitchMowPattern)。",
        "net": "球網顏色", "net_desc": "球門網的顏色 (FSW/Nets)。",
        "goalpost": "球門：模型", "goalpost_desc": "球門模型 (FSW/Goalpost/GoalpostModel)。",
        "goalposttex": "球門：材質", "goalposttex_desc": "球門材質 (FSW/Goalpost/GoalpostColor)。",
        "netmesh": "球網網格", "netmesh_desc": "球網網格 (FSW/NetMesh)。",
        "entrancecam": "入場鏡頭", "entrancecam_desc": "球隊入場的鏡頭 (FSW/Camera/EntranceScene)。",
        "movies_desc": "該指派的開場與結尾影片 (MoviesGBD)；預覽為無聲播放。預設：移除指派。",
        "movies_open_hub": "請在比賽前於比賽中心選擇影片 (R3)。",
        "kits_desc": "球衣將在未來版本推出。",
        "info": "應用程式資料 ({source}, {stamp})",
        "behind": " · 你最後的儲存尚未傳到應用程式",
        "no_data": "沒有應用程式資料：範例數值。請開啟 CG Server 16 後再進入。",
    },
}


SEP_LANG, SEP_FIELD = "^", "~"     # table_string() and token(): never in a text


def token(key: str, **fields) -> str:
    """A text for the menu to put in FIFA's language: "{{key~name:value~...}}" (values without ~ { })."""
    parts = [key] + [f"{name}:{_arg(value)}" for name, value in fields.items()]
    return "{{" + SEP_FIELD.join(parts) + "}}"


def _arg(value) -> str:
    return str(value).replace(SEP_FIELD, "-").replace("{", "(").replace("}", ")")


def render(value: str, lang: str) -> str:
    """value with its tokens replaced by the texts in `lang`, as the menu does (menudata M.tr)."""
    parts = value.split("{{")
    out = parts[0]
    for part in parts[1:]:
        inner, _sep, rest = part.partition("}}")
        args = inner.split(SEP_FIELD)
        word = TEXTS.get(lang, {}).get(args[0]) or TEXTS[DEFAULT].get(args[0]) or args[0]
        for arg in args[1:]:
            name, _colon, arg_value = arg.partition(":")
            word = word.replace("{" + name + "}", arg_value)
        out += word + rest
    return out


def table_string() -> str:
    """The whole table for the menu: languages joined by ^, each "lang~key~text~key~text..."."""
    rows = []
    for lang in LANGUAGES:
        cells = [lang]
        for key, value in TEXTS[lang].items():
            if SEP_LANG in value or SEP_FIELD in value or "{{" in value:
                raise ValueError(f"{lang}.{key}: a text cannot hold ^ ~ {{{{")
            cells += [key, value]
        rows.append(SEP_FIELD.join(cells))
    return SEP_LANG.join(rows)


def text(lang: str, key: str, **fields) -> str:
    """The text `key` in `lang` (English if that language has none), with its {fields} filled in."""
    value = TEXTS.get(lang, {}).get(key) or TEXTS[DEFAULT][key]
    return value.format(**fields) if fields else value


def normalize(code: str | None) -> str | None:
    """'spa', 'spa,es', 'es_ES', 'es-ES' or 'es' -> 'spa'; None if it is none of FIFA 16's languages."""
    if not code:
        return None
    code = code.strip().lower().replace("-", "_").replace(",", "_")
    head = code.split("_", 1)[0]
    if head in LANGUAGES:
        return head
    return TWO_LETTER.get(head)


def from_locale_ini(exedir: str | Path) -> str | None:
    """[LOCALE] DEFAULT_LANGUAGE of <game>/rna.ini (RNA's, read first) or locale.ini ("spa,es", "es,ES")."""
    for name in ("rna.ini", "locale.ini"):
        try:
            lines = (Path(exedir) / name).read_text(encoding="latin-1").splitlines()
        except OSError:
            continue
        for line in lines:
            key, sep, value = line.partition("=")
            if sep and key.strip().upper() == "DEFAULT_LANGUAGE" and normalize(value):
                return normalize(value)
    return None


def from_registry() -> str | None:
    """The installer's "Locale" (e.g. "es_ES") of FIFA 16, or None."""
    try:
        import winreg
    except ImportError:
        return None
    for path in (r"SOFTWARE\WOW6432Node\EA Sports\FIFA 16", r"SOFTWARE\EA Sports\FIFA 16"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                value, _kind = winreg.QueryValueEx(key, "Locale")
        except OSError:
            continue
        found = normalize(str(value))
        if found:
            return found
    return None


def detect(exedir: str | Path | None, app_language: str | None = None) -> str:
    """The game's language as the app can know it before the menu tells (see the module docstring)."""
    return (from_locale_ini(exedir) if exedir else None) or from_registry() or normalize(app_language) or DEFAULT
