/**
 * Two languages, one flat dictionary, no library.
 *
 * An i18n package would bring plural rules, message formats and a loader for
 * strings this app does not have. What it needs is a lookup and `{name}`
 * substitution, and keeping the dictionary as one object means a missing
 * translation is a TypeScript error rather than an English string leaking into
 * a Turkish page.
 */

import { createContext, useContext } from 'react'

export type Lang = 'en' | 'tr'

export const STRINGS = {
  'app.subtitle': {
    en: 'container loading — build a job, solve it, look at it',
    tr: 'konteyner yükleme — iş kur, çöz, incele',
  },
  'tab.new': { en: 'New job', tr: 'Yeni iş' },
  'tab.jobs': { en: 'Jobs', tr: 'İşler' },
  'tab.plan': { en: 'Plan', tr: 'Plan' },
  'tab.needsService': {
    en: 'needs the service running',
    tr: 'servisin çalışıyor olması gerekir',
  },
  'common.loading': { en: 'loading…', tr: 'yükleniyor…' },
  'common.items': { en: 'items', tr: 'kalem' },
  'common.stop': { en: 'stop {n}', tr: 'durak {n}' },

  'scene.doors': { en: 'doors', tr: 'kapılar' },

  'verdict.unchecked': { en: 'unchecked', tr: 'denetlenmedi' },
  'verdict.uncheckedHint': {
    en: 'No validator has seen this plan',
    tr: 'Bu planı hiçbir doğrulayıcı görmedi',
  },
  'verdict.clean': { en: 'all checks pass', tr: 'tüm kontroller geçti' },

  'metric.volume': { en: 'volume', tr: 'hacim' },
  'metric.payload': { en: 'payload', tr: 'tonaj' },
  'metric.placed': { en: 'placed', tr: 'yerleşen' },
  'metric.balance': { en: 'balance', tr: 'denge' },
  'metric.ofVolume': { en: 'of {v} m³', tr: '{v} m³ içinden' },
  'metric.ofPayload': { en: 'of {t} t', tr: '{t} t içinden' },
  'metric.leftBehind': { en: '{n} left behind', tr: '{n} yerleşemedi' },
  'metric.sideways': { en: '{n} mm sideways', tr: '{n} mm yanal' },

  'detail.prompt': {
    en: 'Click a box for its details.',
    tr: 'Detay için bir kutuya tıklayın.',
  },
  'detail.sku': { en: 'sku', tr: 'SKU' },
  'detail.order': { en: 'load order', tr: 'yükleme sırası' },
  'detail.stop': { en: 'stop', tr: 'durak' },
  'detail.size': { en: 'size', tr: 'ölçü' },
  'detail.position': { en: 'position', tr: 'konum' },
  'detail.orientation': { en: 'orientation', tr: 'yönelim' },
  'detail.fromDoors': { en: 'from doors', tr: 'kapıya uzaklık' },

  'view.selection': { en: 'Selection', tr: 'Seçim' },
  'view.leftBehind': { en: 'Left behind', tr: 'Yerleşemeyenler' },
  'view.leftBehindDetail': {
    en: '{n} items did not fit: {reasons}.',
    tr: '{n} kalem sığmadı: {reasons}.',
  },
  'view.demoMode': { en: 'Demo mode', tr: 'Demo modu' },
  'view.demoModeDetail': {
    en: 'No service reachable, so this is the bundled example. Start it with {cmd} to build your own jobs.',
    tr: 'Servise ulaşılamadı, bu paketlenmiş örnek. Kendi işlerinizi kurmak için {cmd} ile başlatın.',
  },
  'view.play': { en: 'Play', tr: 'Oynat' },
  'view.pause': { en: 'Pause', tr: 'Duraklat' },
  'view.replay': { en: 'Replay', tr: 'Tekrar' },
  'view.loaded': { en: '{n} / {total} loaded', tr: '{n} / {total} yüklendi' },
  'view.seeThrough': { en: 'see through', tr: 'şeffaf' },
  'view.openPlan': { en: 'Open plan…', tr: 'Plan aç…' },
  'view.step': { en: 'loading step', tr: 'yükleme adımı' },
  'view.badFile': {
    en: '{name} is not a plan document',
    tr: '{name} bir plan belgesi değil',
  },
  'view.nothing': {
    en: 'no service reachable and no sample bundled',
    tr: 'servise ulaşılamadı ve paketlenmiş örnek yok',
  },

  'form.vehicle': { en: 'Vehicle', tr: 'Araç' },
  'form.jobId': { en: 'job id', tr: 'iş adı' },
  'form.vehicleSpec': {
    en: '{l} × {w} × {h} mm · {v} m³ · {t} t payload',
    tr: '{l} × {w} × {h} mm · {v} m³ · {t} t tonaj',
  },
  'form.cargo': { en: 'Cargo', tr: 'Yük' },
  'form.colItem': { en: 'item', tr: 'kalem' },
  'form.colQty': { en: 'qty', tr: 'adet' },
  'form.colStop': { en: 'stop', tr: 'durak' },
  'form.fragile': { en: 'fragile', tr: 'kırılgan' },
  'form.thisSideUp': { en: 'this side up', tr: 'bu yüz üste' },
  'form.addLine': { en: '+ add line', tr: '+ satır ekle' },
  'form.removeLine': { en: 'remove line', tr: 'satırı sil' },
  'form.gaugeVolume': { en: 'volume', tr: 'hacim' },
  'form.gaugeWeight': { en: 'weight', tr: 'ağırlık' },
  'form.nItems': { en: '{n} items', tr: '{n} kalem' },
  'form.overCapacity': {
    en: 'More cargo than the vehicle holds. That is allowed — the solver packs what fits and reports the rest as left behind.',
    tr: 'Yük araca sığandan fazla. Sorun değil — çözücü sığanı yerleştirir, kalanı yerleşemeyen olarak raporlar.',
  },
  'form.solver': { en: 'Solver', tr: 'Çözücü' },
  'form.corner': { en: 'corner', tr: 'köşe' },
  'form.cornerLayer': { en: 'layer (default)', tr: 'kat kat (varsayılan)' },
  'form.cornerDbl': { en: 'deep-left-bottom', tr: 'dip-sol-alt' },
  'form.cornerContact': { en: 'max contact', tr: 'en çok temas' },
  'form.search': { en: 'search', tr: 'arama' },
  'form.searchFirst': { en: 'first fit', tr: 'ilk uyan' },
  'form.searchBest': { en: 'best fit (slower)', tr: 'en iyi uyan (yavaş)' },
  'form.anneal': { en: 'anneal', tr: 'tavlama' },
  'form.annealOff': { en: 'off', tr: 'kapalı' },
  'form.seconds': { en: '{n} s', tr: '{n} sn' },
  'form.k8': { en: 'delivery reach (K8)', tr: 'teslim erişimi (K8)' },
  'form.k5': { en: 'stacking limits (K5)', tr: 'istif sınırları (K5)' },
  'form.k7': { en: 'centre the load (K7)', tr: 'yükü ortala (K7)' },
  'form.lateral': {
    en: 'sideways balance (experimental)',
    tr: 'yanal denge (deneysel)',
  },
  'form.constraintHint': {
    en: 'Turn a constraint off and solve again to see what it costs — the plans stay side by side under {tab}.',
    tr: 'Bir kısıtı kapatıp tekrar çözün, maliyetini görün — planlar {tab} sekmesinde yan yana kalır.',
  },
  'form.submit': { en: 'Solve and view', tr: 'Çöz ve göster' },
  'form.solving': { en: 'solving…', tr: 'çözülüyor…' },
  'form.searching': { en: 'searching for {n} s…', tr: '{n} sn aranıyor…' },
  'form.needLine': {
    en: 'add at least one item line',
    tr: 'en az bir yük satırı ekleyin',
  },

  'jobs.empty': {
    en: 'No jobs yet. Build one under “New job”.',
    tr: 'Henüz iş yok. “Yeni iş” sekmesinden oluşturun.',
  },
  'jobs.colAlgorithm': { en: 'algorithm', tr: 'algoritma' },
  'jobs.colChecks': { en: 'checks', tr: 'kontroller' },
  'jobs.view': { en: 'view', tr: 'göster' },
  'jobs.clean': { en: 'clean', tr: 'temiz' },
  'jobs.noPlans': {
    en: 'no plans for this job yet',
    tr: 'bu iş için henüz plan yok',
  },
} as const

export type Key = keyof typeof STRINGS

/**
 * Display names for catalogue entries.
 *
 * The names the service sends are part of its data, not of this UI, so they
 * are not translated there -- a plan file that changed wording with the
 * viewer's language would be a poor record. Translating them here keeps the
 * catalogue authoritative and the page readable, and anything unlisted (a
 * benchmark-derived type, a vehicle added later) falls back to the name the
 * service gave.
 */
const CATALOG_NAMES: Record<string, string> = {
  'TIR-1360': '13.60 m tenteli dorse',
  'CNT-20DV': "20 ft kuru yük konteyneri",
  'CNT-40DV': "40 ft kuru yük konteyneri",
  'CNT-40HC': "40 ft yüksek konteyner",
  'EUR-FULL': 'Euro palet, tam yükseklik',
  'EUR-HALF': 'Euro palet, yarım yükseklik',
  'IND-FULL': 'Endüstriyel palet, tam yükseklik',
  'BOX-L': 'Büyük koli',
  'BOX-M': 'Orta koli',
  'BOX-S': 'Küçük koli',
  'CRATE-FRAGILE': 'Kırılgan cam kasa',
  'DRUM-200L': '200 L çelik varil',
}

export function displayName(lang: Lang, code: string, fallback: string): string {
  if (lang === 'en') return fallback
  return CATALOG_NAMES[code] ?? fallback
}

export function translate(
  lang: Lang,
  key: Key,
  vars?: Record<string, string | number>,
): string {
  const template = STRINGS[key][lang]
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    name in vars ? String(vars[name]) : whole,
  )
}

export interface LanguageContextValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: Key, vars?: Record<string, string | number>) => string
}

export const LanguageContext = createContext<LanguageContextValue>({
  lang: 'en',
  setLang: () => {},
  t: (key, vars) => translate('en', key, vars),
})

export const useT = () => useContext(LanguageContext)

const STORAGE_KEY = 'loadza.lang'

/** Remembered choice, else the browser's preference, else English. */
export function initialLanguage(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'tr' || stored === 'en') return stored
  return navigator.language?.toLowerCase().startsWith('tr') ? 'tr' : 'en'
}

export function rememberLanguage(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang)
}
