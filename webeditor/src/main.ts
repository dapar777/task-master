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
    const root = document.documentElement
    for (const [k, v] of Object.entries(map)) {
      if (k.startsWith('--crepe-') || k.startsWith('--tm-')) root.style.setProperty(k, v)
    }
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
}

main().catch((e) => {
  // bez konzole hostitele by chyba zmizela — ukázat ji přímo v okně
  const pre = document.createElement('pre')
  pre.textContent = 'Editor se nepodařilo spustit: ' + (e instanceof Error ? e.message : String(e))
  document.body.appendChild(pre)
})
