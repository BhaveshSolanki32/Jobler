import re
import copy

_BS_RE = re.compile(r'(<browser_state>)(.*?)(</browser_state>)', re.DOTALL)

_GENERIC_MARKERS = ['role=dialog', 'aria-modal=true', 'aria-modal="true"']


def _detect_modal(state_text: str, extra_markers: list) -> bool:
    return any(m in state_text for m in _GENERIC_MARKERS + extra_markers)


def _extract_modal_subtree(state_text: str, all_markers: list) -> str:
    lines = state_text.split('\n')

    modal_line_idx = None
    modal_indent = 0
    for i, line in enumerate(lines):
        if any(m in line for m in all_markers):
            modal_line_idx = i
            modal_indent = len(line) - len(line.lstrip('\t '))
            break

    if modal_line_idx is None:
        return state_text

    modal_lines = [lines[modal_line_idx]]
    for line in lines[modal_line_idx + 1:]:
        if not line.strip():
            modal_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip('\t '))
        if indent <= modal_indent:
            break
        modal_lines.append(line)

    header = [
        line for line in lines
        if line.startswith('<page_stats>')
        or line.startswith('Current tab:')
        or line.startswith('Available tabs:')
        or line.startswith('Tab ')
    ]
    parts = header + ['', 'Interactive elements:', '[Start of page]'] + modal_lines + ['[End of page]']
    return '\n'.join(parts)


def filter_browser_state(state_text: str, meta: dict) -> str:
    extra = meta.get('modal_markers', [])
    if not _detect_modal(state_text, extra):
        return state_text
    return _extract_modal_subtree(state_text, _GENERIC_MARKERS + extra)


def _replace_content(msg, new_content: str):
    try:
        return msg.model_copy(update={'content': new_content})
    except Exception:
        m = copy.copy(msg)
        try:
            object.__setattr__(m, 'content', new_content)
        except Exception:
            m.content = new_content
        return m


def apply_to_messages(messages: list, meta: dict) -> list:
    result = []
    for msg in messages:
        content = getattr(msg, 'content', None)
        if content and '<browser_state>' in content:
            new_content = _BS_RE.sub(
                lambda m: m.group(1) + filter_browser_state(m.group(2), meta) + m.group(3),
                content,
            )
            result.append(_replace_content(msg, new_content))
        else:
            result.append(msg)
    return result
