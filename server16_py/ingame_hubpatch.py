"""Text patches that add the CGFS16 tile to the main hub and its flow to the navigation.

Everything we add sits between BEGIN/END marker comments, so it can be found (idempotent
install) and removed (uninstall) without touching anything else in files that FIP or
other mods also edit. A tile we change is kept, commented out, inside the markers and
put back by unpatch.

  layout/mainhubcfg.xml  -> a tile with DESTINATION=<EVENT> (the hub sends it as a nav event)  [retired]
  nav/mainfeflow.nav     -> transition <EVENT> -> state <FLOW_STATE> (external flow file)        [retired]
  nav/<FLOW_FILE>        -> our flow: loads the screen, "back" returns to the main menu
  NAVS (kickoffhubflow, careermode/playmatchflow, fut/quicksettingsflow)
                         -> R3 on the pre-match hub: event KICKOFF_EVENT -> a state running our flow

Standard library only: the CG Server 16 carries a byte-identical copy (server16_py/ingame_hubpatch.py)
to install the menu without this project's toolchain (modinstall.py).
"""
import json
import re

TAG = 'CGFS16-INGAME'
EVENT = 'CGFS16Menu'
FLOW_STATE = 'cgfs16MenuFlow'
FLOW_FILE = 'cgfs16menuflow.nav'
SCREEN_VIEW = 'game/screens/cgfs16/CGFS16Menu'  # loadView path (the file is <lower>.big)
TILE_ID = 9216          # not used by any FIFA 16 hub config
TILE_IMAGE = 'CGFS16Menu'  # FG_PATH -> data/ui/imgAssets/tiles/mainHub/cgfs16menu.dds


def _nl(text):
    return '\r\n' if '\r\n' in text else '\n'


def strip_marked(text, comment_open, comment_close):
    """text without our BEGIN..END blocks (and, inside them, original content is restored)."""
    begin = re.escape(f'{comment_open} {TAG} BEGIN')
    end = re.escape(f'{TAG} END {comment_close}')
    pat = re.compile(r'[ \t]*' + begin + r'.*?' + end + r'[ \t]*(?:\r?\n)?', re.S)

    def restore(m):
        orig = re.search(re.escape(f'{TAG} ORIGINAL') + r'\r?\n(.*?)' + re.escape(f'{TAG} ORIGINAL END'),
                         m.group(0), re.S)
        return orig.group(1) if orig else ''
    return pat.sub(restore, text)


def is_patched(text):
    return f'{TAG} BEGIN' in text


# --- layout/mainhubcfg.xml ------------------------------------------------------------

# Variant "editteams": Customise > Edit Teams. Team Management (846 wide at 109,278) becomes a
# square tile like its twin in the Customise panel, and ours takes the freed square at 537,278.
TEAM_MGMT_RE = re.compile(
    r'(?P<indent>[ \t]*)<tile>\s*<tileid tileid="1216"[^>]*/>\s*'
    r'<settings FILE_PATH="TILE" WIDTH="846" HEIGHT="310" X="109" Y="278"\s*/>.*?</tile>[ \t]*\r?\n', re.S)
PANEL7_COUNT_RE = re.compile(r'(<panel_7\b[^>]*>\s*<entries numberoftiles=")(\d+)("\s*/>)')
COUNT_MARK_RE = re.compile(r'(<entries numberoftiles=")\d+("\s*/>)<!-- ' + re.escape(TAG) + r' BEGIN count '
                           + re.escape(TAG) + r' ORIGINAL (\d+) ' + re.escape(f'{TAG} ORIGINAL END {TAG} END -->'))


def our_tile(indent, nl, title='CGFS16', story='Server 16 dentro del juego'):
    i1, i2 = indent, indent + '  '
    lines = [
        f'{i1}<tile>',
        f'{i2}<tileid tileid="{TILE_ID}" NAME="CGFS16 MENU" PARAM="" />',
        f'{i2}<settings FILE_PATH="TILE" WIDTH="418" HEIGHT="310" X="537" Y="278" />',
        f'{i2}<main_tile FG_PATH="{TILE_IMAGE}" DESTINATION="{EVENT}" />',
        f'{i2}<number_of_subtiles LENGTH="0" />',
        f'{i2}<data ID="TITLE" TYPE="title" PARAM="{title}" TRANSLATE="FALSE" />',
        f'{i2}<data TYPE="text" PARAM="{xml_escape_ascii(story)}" TRANSLATE="FALSE" FORMAT="SS" WIDTH="260" '
        f'HEIGHT="60" X="18" REL_TARGET="TITLE" REL_Y="-17" />',
        f'{i1}</tile>',
    ]
    return nl.join(lines) + nl


def xml_escape_ascii(s):
    """The hub file is us-ascii and no FIFA 16 hub file uses entities or character references
    (unknown whether the game's parser reads them): plain ASCII only."""
    if any(ord(c) > 127 for c in s) or any(c in s for c in '&"<>'):
        raise ValueError(f'hub text must be plain ASCII without &"<>: {s!r}')
    return s


def patch_hub(text):
    if is_patched(text):
        return text
    nl = _nl(text)
    m = TEAM_MGMT_RE.search(text)
    if not m:
        raise ValueError('mainhubcfg.xml: Edit Teams > Team Management tile (1216, 846x310 at 109,278) not found')
    original = m.group(0)
    if '--' in original:
        raise ValueError('mainhubcfg.xml: the Team Management tile holds "--" and cannot be kept in a comment')
    indent = m.group('indent')
    square = original.replace('WIDTH="846"', 'WIDTH="418"', 1)
    square = re.sub(r'<main_tile FG_PATH="TeamSheets"', '<main_tile BG_ICON="TeamSheets_Square"', square, 1)
    # story text as wide as on the square Team Management tile of the Customise panel
    square = re.sub(r'(PARAM="MM_CUSTOMISE_EDIT_TEAMMANAGE_STORY" FORMAT="SS" WIDTH=")\d+', r'\g<1>260', square, 1)
    block = (f'{indent}<!-- {TAG} BEGIN: Team Management made square, CGFS16 tile added' + nl +
             f'{TAG} ORIGINAL' + nl + original + f'{TAG} ORIGINAL END -->' + nl +
             square + our_tile(indent, nl) +
             f'{indent}<!-- {TAG} END -->' + nl)
    text = text[:m.start()] + block + text[m.end():]
    c = PANEL7_COUNT_RE.search(text)
    if c:  # one tile more; the old count in a comment right after the element, for unpatch
        old = int(c.group(2))
        text = (text[:c.start()] + c.group(1) + str(old + 1) + c.group(3) +
                f'<!-- {TAG} BEGIN count {TAG} ORIGINAL {old} {TAG} ORIGINAL END {TAG} END -->'
                + text[c.end():])
    return text


def unpatch_hub(text):
    # the count first: strip_marked would leave its number behind as text
    text = COUNT_MARK_RE.sub(lambda m: m.group(1) + m.group(3) + m.group(2), text)
    return strip_marked(text, '<!--', '-->')


# --- nav/mainfeflow.nav (JSON with /* */ comments) ------------------------------------

STADIUMS_EVENT_RE = re.compile(r'\{\s*"event"\s*:\s*"Stadiums"\s*,\s*"targets"\s*:\s*\[\s*"stadiumsFlow"\s*\]\s*\}')
STADIUMS_STATE_RE = re.compile(r'\{\s*"name"\s*:\s*"stadiumsFlow"\s*,\s*"type"\s*:\s*"external"\s*,'
                               r'\s*"file"\s*:\s*"/stadiumsFlow\.nav"\s*,\s*"outputs"\s*:\s*\{[^{}]*\}\s*\}', re.I)


def _insert_after(text, m, new_block):
    """Inserts ',<new_block>' on the lines after match m, indented like the line m starts on."""
    nl = _nl(text)
    line_start = text.rfind('\n', 0, m.start()) + 1
    indent = re.match(r'[ \t]*', text[line_start:]).group(0)
    end = text.find('\n', m.end())
    end = len(text) if end < 0 else end + 1
    block = (f'{indent}/* {TAG} BEGIN */{nl}{indent},{new_block}{nl}{indent}/* {TAG} END */{nl}')
    return text[:end] + block + text[end:]


def patch_nav(text):
    if is_patched(text):
        return text
    m = STADIUMS_EVENT_RE.search(text)
    if not m:
        raise ValueError('mainfeflow.nav: the "Stadiums" transition to anchor on was not found')
    event = m.group(0).replace('"Stadiums"', f'"{EVENT}"').replace('"stadiumsFlow"', f'"{FLOW_STATE}"')
    text = _insert_after(text, m, event)
    m = STADIUMS_STATE_RE.search(text)
    if not m:
        raise ValueError('mainfeflow.nav: the "stadiumsFlow" state to anchor on was not found')
    state = re.sub(r'"stadiumsFlow"', f'"{FLOW_STATE}"', m.group(0))
    state = re.sub(r'"/stadiumsFlow\.nav"', f'"/{FLOW_FILE}"', state, flags=re.I)
    return _insert_after(text, m, state)


def unpatch_nav(text):
    return strip_marked(text, '/*', '*/')


def flow_nav(screen_view=SCREEN_VIEW, nl='\r\n'):
    """Our flow: the screen with FIP's usual background; back leaves through output "back"."""
    flow = {
        'name': FLOW_STATE,
        'initial': {'targets': ['cgfs16Menu']},
        'states': [{
            'name': 'cgfs16Menu',
            'onEnter': [['loadView', ['screen', screen_view]], ['loadView', ['background', 'BOOTFLOW']]],
            'onExit': [['unloadView', ['screen', screen_view]], ['unloadView', ['background']]],
            'transitions': [{'event': 'back', 'targets': ['back']}],
        }],
    }
    return json.dumps(flow, indent='\t').replace('\n', nl) + nl


# --- lenient reader (validation only) -------------------------------------------------

def nav_load(text):
    """Parses EA's nav JSON: /* */ and // comments, trailing commas."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('/*', i):
            i = text.index('*/', i + 2) + 2
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    clean = re.sub(r',(\s*[\]}])', r'\1', ''.join(out))
    return json.loads(clean)


def find_state(node, name):
    """The state dict called name anywhere in a parsed flow."""
    if isinstance(node, dict):
        if node.get('name') == name:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            hit = find_state(v, name)
            if hit is not None:
                return hit
    return None


def transitions_for(node, event, path=()):
    """[(owner state name, transition)] for every transition on event."""
    hits = []
    if isinstance(node, dict):
        for t in node.get('transitions', []) if isinstance(node.get('transitions'), list) else []:
            if isinstance(t, dict) and t.get('event') == event:
                hits.append((node.get('name'), t))
        for v in node.values():
            hits += transitions_for(v, event)
    elif isinstance(node, list):
        for v in node:
            hits += transitions_for(v, event)
    return hits


# --- R3 on the pre-match hub: the flows that load KickOffHub (entries.py has the movie hook) -------

KICKOFF_NAV = 'data/ui/nav/kickoffhubflow.nav'
CAREER_NAV = 'data/ui/nav/careermode/playmatchflow.nav'
FUT_NAV = 'data/ui/nav/fut/quicksettingsflow.nav'
KICKOFF_EVENT = 'CGFS16MenuKickOff'
KICKOFF_STATE = 'cgfs16MenuFromKickOff'

SETTINGS_EVENT_RE = re.compile(r'\{\s*"event"\s*:\s*"SettingsGame"\s*,\s*"targets"\s*:\s*\[\s*"SettingsGame"\s*\]\s*\}')


def _external_state_re(name, file, inputs=False):
    """An external state block {"name", "type", "file"[, "inputs":{..}], "outputs":{..}} (flat inner objects)."""
    body = (r'\{\s*"name"\s*:\s*"' + name + r'"\s*,\s*"type"\s*:\s*"external"\s*,\s*"file"\s*:\s*"'
            + re.escape(file) + r'"\s*,')
    if inputs:
        body += r'\s*"inputs"\s*:\s*\{[^{}]*\}\s*,'
    return re.compile(body + r'\s*"outputs"\s*:\s*\{[^{}]*\}\s*\}', re.I)


# flow -> (the KickOffHub's state, the sibling state block to insert ours after)
NAVS = {
    KICKOFF_NAV: ('QuickSettings', _external_state_re('QuickSettingsStadiumPan', '/stadiumPanFlow.nav')),
    CAREER_NAV: ('KickOffHub', _external_state_re('HelpFlow', '/helpFlow.nav', inputs=True)),
    FUT_NAV: ('QuickSettings', _external_state_re('TeamManagementFlow', '/editTeamSheetFlow.nav')),
}


def patch_entry_nav(rel, text):
    if is_patched(text):
        return text
    hub, anchor = NAVS[rel]
    name = rel.rsplit('/', 1)[-1]
    m = SETTINGS_EVENT_RE.search(text)
    if not m:
        raise ValueError(f'{name}: the "SettingsGame" transition to anchor on was not found')
    text = _insert_after(text, m, f'{{\t"event":"{KICKOFF_EVENT}", "targets":["{KICKOFF_STATE}"]\t}}')
    m = anchor.search(text)
    if not m:
        raise ValueError(f'{name}: the state to anchor on was not found ({anchor.pattern[:60]}...)')
    state = (f'{{ "name":"{KICKOFF_STATE}", "type":"external", "file":"/{FLOW_FILE}",'
             f' "outputs":{{ "back":"{hub}" }} }}')
    return _insert_after(text, m, state)


def check_entry_nav(rel, text):
    hub, _anchor = NAVS[rel]
    name = rel.rsplit('/', 1)[-1]
    flow = nav_load(text)
    hits = transitions_for(flow, KICKOFF_EVENT)
    if len(hits) != 1 or hits[0][1].get('targets') != [KICKOFF_STATE]:
        raise ValueError(f'{name}: expected one {KICKOFF_EVENT} transition, got {hits}')
    hub_state = find_state(flow, hub)
    if not hub_state or not any(t.get('event') == KICKOFF_EVENT for t in hub_state.get('transitions', [])):
        raise ValueError(f'{name}: the {KICKOFF_EVENT} transition is not in the hub state {hub}')
    state = find_state(flow, KICKOFF_STATE)
    if not state or state.get('file', '').lower() != '/' + FLOW_FILE or state.get('outputs') != {'back': hub}:
        raise ValueError(f'{name}: state {KICKOFF_STATE} missing or wrong: {state}')


def entry_patchers(rel):
    """(patch, unpatch) of one of NAVS."""
    return (lambda text: patch_entry_nav(rel, text)), unpatch_nav


# --- every patched file -------------------------------------------------------------------------

HUB = 'data/ui/layout/mainhubcfg.xml'
NAV = 'data/ui/nav/mainfeflow.nav'
# what is installed: R3 on the pre-match hub
PATCHES = {rel: entry_patchers(rel) for rel in NAVS}
# no longer installed, only taken out of a game that still has it: the CGFS16 tile in Customise > Edit Teams
# (until 2026-11-11; R3 on the match hub is enough, the user)
RETIRED = {HUB: unpatch_hub, NAV: unpatch_nav}
# rel -> unpatch of everything an install of ours may have patched (modinstall.install / uninstall)
UNPATCH = dict(RETIRED, **{rel: unpatch for rel, (_patch, unpatch) in PATCHES.items()})


def check_patched(rel, text):
    """Raises ValueError if a patched file does not have what our flows need."""
    if rel == NAV:
        flow = nav_load(text)
        hits = transitions_for(flow, EVENT)
        if len(hits) != 1 or hits[0][1].get('targets') != [FLOW_STATE]:
            raise ValueError(f'{rel}: expected one {EVENT} transition, got {hits}')
        state = find_state(flow, FLOW_STATE)
        if not state or state.get('file', '').lower() != '/' + FLOW_FILE:
            raise ValueError(f'{rel}: state {FLOW_STATE} missing or wrong: {state}')
    elif rel in NAVS:
        check_entry_nav(rel, text)
    elif rel == HUB:
        # only panel_7: FIFA 16's own file is not strict XML elsewhere (a duplicate attribute, line 846)
        import xml.etree.ElementTree as ET
        m = re.search(r'<panel_7[ >].*?</panel_7>', text, re.S)
        if not m:
            raise ValueError(f'{rel}: no panel_7')
        panel = ET.fromstring(m.group(0).encode('latin-1'))
        ids = [t.find('tileid').get('tileid') for t in panel.findall('tile')]
        if str(TILE_ID) not in ids:
            raise ValueError(f'{rel}: our tile is not in panel_7 ({ids})')
        if int(panel.find('entries').get('numberoftiles')) < len(ids):
            raise ValueError(f'{rel}: numberoftiles below the number of tiles in panel_7')
