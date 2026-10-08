/**
 * Sdílený editor markdownu nad Milkdown Crepe.
 *
 * Rozhraní pro hostitele je úmyslně prosté a stejné pro obě aplikace:
 *
 *   window.TM.setMarkdown(md)      – nahradí obsah (bez hlášení změny)
 *   window.TM.getMarkdown()        – aktuální markdown
 *   window.TM.exec(cmd, arg?)      – formátovací příkaz (viz COMMANDS)
 *   window.TM.insertText(text)     – vloží text na pozici kurzoru
 *   window.TM.setTheme(vars)       – CSS proměnné --crepe-* / --tm-* od hostitele
 *   window.TM.setReadonly(bool)
 *   window.TM.focus()
 *   window.TM.isReady()
 *
 * Události jdou na `window.TMHost`, který dosadí hostitel:
 *   Android – objekt z addJavascriptInterface("TMHost"),
 *   Qt      – objekt z QWebChannel přes TM.bind() (dosadí se asynchronně,
 *             proto `emit` zkouší existenci při každém volání a `onReady`
 *             se po bind() pošle i zpětně).
 *
 *   TMHost.onReady()        – editor je připravený přijímat obsah
 *   TMHost.onChange(md)     – uživatel změnil obsah (ne při setMarkdown)
 */
import { Crepe } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'
import { callCommand, insert, replaceAll } from '@milkdown/kit/utils'
import {
  insertHrCommand,
  toggleEmphasisCommand,
  toggleInlineCodeCommand,
  toggleLinkCommand,
  toggleStrongCommand,
  turnIntoTextCommand,
  wrapInBlockquoteCommand,
  wrapInBulletListCommand,
  wrapInHeadingCommand,
  wrapInOrderedListCommand,
} from '@milkdown/kit/preset/commonmark'
import { toggleStrikethroughCommand } from '@milkdown/kit/preset/gfm'

type Host = {
  onReady?: () => void
  onChange?: (md: string) => void
  /** výška obsahu editoru v CSS px — hostitel bez vlastního rolování (Android
   *  WebView ve sloupci) podle ní nastaví výšku pohledu; Qt ji nepotřebuje */
  onHeight?: (px: number) => void
  /** kurzor je v editoru (Android: klávesnice → „nad klávesnicí jen editor“) */
  onFocus?: (focused: boolean) => void
  /** svislá poloha kurzoru/výběru v CSS px od horního okraje stránky — hostitel
   *  ho udrží nad klávesnicí (stránka sama neroluje) */
  onCaret?: (top: number, bottom: number) => void
  /** otevřený popup (lomítkové menu, lišta nad výběrem) — hostitel doroluje,
   *  aby byl celý vidět */
  onPopup?: (top: number, bottom: number) => void
}

declare global {
  interface Window {
    TM: typeof TM
    TMHost?: Host
  }
}

let crepe: Crepe | null = null
let ready = false
let suppress = 0 // > 0 = změny obsahu nehlásit (setMarkdown)

function emit(name: 'onReady'): void
function emit(name: 'onChange', md: string): void
function emit(name: 'onHeight', px: number): void
function emit(name: 'onFocus', focused: boolean): void
function emit(name: 'onCaret', top: number, bottom: number): void
function emit(name: 'onPopup', top: number, bottom: number): void
function emit(name: keyof Host, ...args: unknown[]): void {
  const h = window.TMHost
  const fn = h && (h[name] as ((...a: unknown[]) => void) | undefined)
  if (typeof fn === 'function') fn.apply(h, args)
}

type Action = Parameters<Crepe['editor']['action']>[0]

function run(action: Action): void {
  if (!crepe) return
  crepe.editor.action(action)
  focusEditor()
}

/** Názvy příkazů = `fmt.*` z desktopních COMMAND_DEFS, aby mapování bylo 1:1. */
const COMMANDS: Record<string, (arg?: unknown) => void> = {
  'fmt.bold': () => run(callCommand(toggleStrongCommand.key)),
  'fmt.italic': () => run(callCommand(toggleEmphasisCommand.key)),
  'fmt.strike': () => run(callCommand(toggleStrikethroughCommand.key)),
  'fmt.code': () => run(callCommand(toggleInlineCodeCommand.key)),
  'fmt.h1': () => run(callCommand(wrapInHeadingCommand.key, 1)),
  'fmt.h2': () => run(callCommand(wrapInHeadingCommand.key, 2)),
  'fmt.h3': () => run(callCommand(wrapInHeadingCommand.key, 3)),
  'fmt.paragraph': () => run(callCommand(turnIntoTextCommand.key)),
  'fmt.bullet': () => run(callCommand(wrapInBulletListCommand.key)),
  'fmt.numbered': () => run(callCommand(wrapInOrderedListCommand.key)),
  'fmt.quote': () => run(callCommand(wrapInBlockquoteCommand.key)),
  'fmt.hr': () => run(callCommand(insertHrCommand.key)),
  'fmt.link': (arg) => {
    const href = typeof arg === 'string' ? arg : (arg as { href?: string } | undefined)?.href
    if (href) run(callCommand(toggleLinkCommand.key, { href }))
  },
}

function focusEditor(): void {
  document.querySelector<HTMLElement>('#editor .ProseMirror')?.focus()
}

/**
 * Výška obsahu = výška `.milkdown` (text + vnitřní okraje), ne `scrollHeight`
 * dokumentu: ten je omezený zdola výškou okna, takže by pohled jen rostl
 * a nikdy se nezmenšil.
 */
let lastHeight = -1
function reportHeight(): void {
  const el = document.querySelector<HTMLElement>('#editor .milkdown')
  if (!el) return
  const h = Math.ceil(el.getBoundingClientRect().height)
  if (h !== lastHeight) {
    lastHeight = h
    emit('onHeight', h)
  }
}

const TM = {
  setMarkdown(md: string): void {
    if (!crepe) return
    suppress += 1
    try {
      crepe.editor.action(replaceAll(md ?? '', true))
    } finally {
      // listener markdownUpdated běží v rámci transakce; uvolnit až po dalším
      // tiku, kdyby ho Crepe odložil
      setTimeout(() => { suppress = Math.max(0, suppress - 1) }, 0)
    }
  },
  getMarkdown(): string {
    return crepe ? crepe.getMarkdown() : ''
  },
  exec(cmd: string, arg?: unknown): boolean {
    const fn = COMMANDS[cmd]
    if (!fn) return false
    fn(arg)
    return true
  },
  insertText(text: string): void {
    run(insert(text ?? ''))
  },
  setTheme(vars: Record<string, string> | string): void {
    const map = typeof vars === 'string' ? (JSON.parse(vars) as Record<string, string>) : vars
    // Téma Crepe definuje všechny --crepe-* proměnné pod `.milkdown {}`, takže
    // hodnota nastavená na <html> by se k editoru nedostala (přebije ji vlastní
    // definice potomka). Proto vlastní <style> s pravidlem na `:root, .milkdown`
    // vložený AŽ ZA CSS bundlu: stejná specificita, pozdější vyhrává.
    const decls = Object.entries(map)
      .filter(([k]) => k.startsWith('--crepe-') || k.startsWith('--tm-'))
      .map(([k, v]) => `${k}: ${v};`)
      .join(' ')
    let style = document.getElementById('tm-theme') as HTMLStyleElement | null
    if (!style) {
      style = document.createElement('style')
      style.id = 'tm-theme'
      document.head.appendChild(style)
    } else {
      document.head.appendChild(style) // znovu nakonec, kdyby mezitím přibylo CSS
    }
    style.textContent = `:root, .milkdown { ${decls} }`
  },
  setReadonly(on: boolean): void {
    crepe?.setReadonly(!!on)
  },
  focus(): void {
    focusEditor()
  },
  /** Hostitel (Qt) zavolá po navázání kanálu; onReady dostane i zpětně. */
  bind(host: Host): void {
    window.TMHost = host
    if (ready) emit('onReady')
  },
  isReady(): boolean {
    return ready
  },
}

window.TM = TM

async function main(): Promise<void> {
  const root = document.getElementById('editor')!
  crepe = new Crepe({
    root,
    defaultValue: '',
    featureConfigs: {
      [Crepe.Feature.Placeholder]: { text: 'Popis úkolu…', mode: 'doc' },
    },
  })
  crepe.on((api) => {
    api.markdownUpdated((_ctx, md, prev) => {
      if (suppress > 0 || md === prev) return
      emit('onChange', md)
    })
  })
  await crepe.create()
  ready = true
  emit('onReady')
  const editorEl = document.querySelector<HTMLElement>('#editor .milkdown')
  if (editorEl && typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => reportHeight()).observe(editorEl)
  }
  reportHeight()
  watchFocusCaretAndPopups()
}

/**
 * Fokus, kurzor a popupy pro hostitele bez vlastního rolování (Android).
 * Pozice jsou v CSS px od horního okraje stránky; stránka sama neroluje
 * (výška pohledu = obsah), takže odpovídají poloze uvnitř pohledu.
 */
function watchFocusCaretAndPopups(): void {
  const pm = document.querySelector<HTMLElement>('#editor .ProseMirror')
  if (!pm) return
  let focused = false
  // fokus sledovat na dokumentu: stav se odvodí z document.activeElement, takže
  // sedí i když fokus přeskočí mezi vnitřními prvky editoru (lišta, odkaz)
  function syncFocus(): void {
    const now = !!document.activeElement && pm.contains(document.activeElement)
    if (now === focused) return
    focused = now
    emit('onFocus', now)
    if (now) scheduleCaret()
  }
  document.addEventListener('focusin', syncFocus)
  document.addEventListener('focusout', () => setTimeout(syncFocus, 0))
  window.addEventListener('blur', () => setTimeout(syncFocus, 0))

  let caretPending = false
  let lastCaret = ''
  function caretRect(): { top: number; bottom: number } | null {
    const sel = document.getSelection()
    if (!sel || sel.rangeCount === 0) return null
    const range = sel.getRangeAt(0)
    let r = range.getBoundingClientRect()
    if (r.height === 0) {
      // sbalený kurzor v prázdném bloku: vzít prvek, ve kterém stojí
      const node = range.startContainer
      const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
      if (!el) return null
      r = el.getBoundingClientRect()
    }
    return { top: Math.floor(r.top + window.scrollY), bottom: Math.ceil(r.bottom + window.scrollY) }
  }
  function scheduleCaret(): void {
    if (caretPending) return
    caretPending = true
    requestAnimationFrame(() => {
      caretPending = false
      if (!focused) return
      const c = caretRect()
      if (!c) return
      const key = `${c.top}:${c.bottom}`
      if (key === lastCaret) return
      lastCaret = key
      emit('onCaret', c.top, c.bottom)
    })
  }
  document.addEventListener('selectionchange', scheduleCaret)
  // při psaní se kurzor posouvá i bez změny výběru (nový řádek) → hlásit i po vstupu
  pm.addEventListener('input', scheduleCaret)

  // popupy Crepe (lomítkové menu, lišta nad výběrem) se ukazují přes data-show;
  // poloha je od floating-ui až o chvíli později, proto krátké zpoždění
  const root = document.getElementById('editor')
  if (!root || typeof MutationObserver === 'undefined') return
  new MutationObserver((muts) => {
    for (const m of muts) {
      const el = m.target as HTMLElement
      if (el.getAttribute('data-show') !== 'true') continue
      setTimeout(() => {
        if (el.getAttribute('data-show') !== 'true') return
        const r = el.getBoundingClientRect()
        if (r.height > 0) emit('onPopup', Math.floor(r.top + window.scrollY), Math.ceil(r.bottom + window.scrollY))
      }, 50)
    }
  }).observe(root, { subtree: true, attributes: true, attributeFilter: ['data-show'] })
}

main().catch((e) => {
  // bez konzole hostitele by chyba zmizela — ukázat ji přímo v okně
  const pre = document.createElement('pre')
  pre.textContent = 'Editor se nepodařilo spustit: ' + (e instanceof Error ? e.message : String(e))
  document.body.appendChild(pre)
})
