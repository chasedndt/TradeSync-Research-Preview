/**
 * What the notification setup says in each real state, and the two facts about iPhones that decide everything.
 *
 * The rule the wording follows: say what is true now, and the one thing to do next. "Notifications unavailable"
 * is not an instruction; "add TradeSync to the Home Screen first, then come back" is.
 */

import type { PermissionState, PushSupport } from '../../pwa/pushSupport'

export type Action = 'install' | 'ask' | 'subscribe' | 'browser_settings' | 'server_key' | 'server_contact' | 'none'

export interface Advice {
  headline: string
  detail: string
  action: Action
}

/** The iPhone and iPad requirement, stated plainly because it is the step that surprises people. */
export const IOS_REQUIREMENT =
  'On an iPhone or iPad, notifications work only after the dashboard is added to the Home Screen: open it in '
  + 'Safari, tap Share, then Add to Home Screen, and open it from that icon. A Safari tab cannot receive them. '
  + 'This is standards-based Web Push, so no Xcode project, no App Store listing and no Apple Developer '
  + 'membership are needed.'

/** What a Home Screen web app is, and is not. */
export const INSTALL_NOTE =
  'Installing adds an icon that opens the dashboard without browser chrome. It is the same dashboard on the '
  + 'same machine — it downloads no app and grants no trading, signing or wallet authority.'

/** Where alerts go once a browser is subscribed, and what a tap does. */
export const DELIVERY_NOTE =
  'While Web Push can send, alerts for the phone this browser belongs to arrive here instead of the ntfy app. '
  + 'Tapping one opens the dashboard and marks it seen in the delivery ledger. A subscription its push service '
  + 'reports gone is marked expired, and once the phone has no subscribed browser left, it goes back to ntfy.'

/** Why a subscribed browser can still receive nothing: the sender has no contact yet. */
export const CONTACT_NOTE =
  'Push services are given a contact for the sender, and Apple’s refuses a push without one. Until '
  + 'MOBILE_WEB_PUSH_SUBJECT is a mailto: address or an https: URL, alerts keep going through ntfy. The command '
  + 'below stores it through the desktop prompt; the dashboard only ever shows whether it is set.'

export const CACHE_NOTE =
  'The installed app never stores prices, positions or paper numbers. Without a connection it shows one page '
  + 'saying so, because a kept copy of a market number is a wrong number.'

const PERMISSION_WORDS: Record<PermissionState, string> = {
  default: 'not asked yet',
  granted: 'allowed',
  denied: 'blocked in this browser',
}

export const permissionWord = (permission: PermissionState): string => PERMISSION_WORDS[permission]

const SUPPORT_WORDS: Record<PushSupport, string> = {
  supported: 'this browser can show notifications',
  needs_home_screen: 'add to the Home Screen first',
  unsupported: 'this browser cannot show notifications',
}

export const supportWord = (support: PushSupport): string => SUPPORT_WORDS[support]

/** Whether the server sends Web Push at all right now, and if not, what it is waiting for. */
export function senderWord(configured: boolean, senderReady: boolean): string {
  if (senderReady) return 'ready'
  return configured ? 'waiting for a contact address' : 'needs the key pair'
}

/**
 * The one thing to say, given the browser, the permission, whether a key pair is configured on the server, whether
 * this browser is already subscribed, and whether the server can send. Order matters: a phone that cannot
 * subscribe at all is told that before it is told about anything missing on the server.
 */
export function advice(
  support: PushSupport,
  permission: PermissionState,
  configured: boolean,
  subscribed: boolean,
  senderReady: boolean,
): Advice {
  if (support === 'needs_home_screen') {
    return {
      headline: 'Add TradeSync to the Home Screen first',
      detail: IOS_REQUIREMENT,
      action: 'install',
    }
  }
  if (support === 'unsupported') {
    return {
      headline: 'This browser cannot show notifications',
      detail: 'It has no service worker or no Push API. Use a current Chrome, Edge, Firefox or Safari, or keep '
        + 'using the ntfy app on the phone, which needs none of this.',
      action: 'none',
    }
  }
  if (!configured) {
    return {
      headline: 'No Web Push key pair is configured on this PC',
      detail: 'A browser cannot subscribe until the operator generates a VAPID key pair and sets it in '
        + 'runtime.env. The command below makes one on this PC and prints both halves; nothing is generated, '
        + 'stored or sent by the dashboard.',
      action: 'server_key',
    }
  }
  if (permission === 'denied') {
    return {
      headline: 'Notifications are blocked for this site',
      detail: 'The browser will not ask again until you change it: open the padlock or site settings beside the '
        + 'address, allow notifications for this site, then reload this page.',
      action: 'browser_settings',
    }
  }
  if (permission === 'default') {
    return {
      headline: 'This browser has not been asked yet',
      detail: 'Choose Allow notifications. The browser asks once; if you dismiss it, it will not ask again '
        + 'until the site permission is reset.',
      action: 'ask',
    }
  }
  if (!subscribed) {
    return {
      headline: 'Notifications are allowed, this browser is not subscribed',
      detail: `Choose the enrolled phone this browser belongs to and subscribe it. ${DELIVERY_NOTE}`,
      action: 'subscribe',
    }
  }
  if (!senderReady) {
    return {
      headline: 'This browser is subscribed, but nothing is sent to it yet',
      detail: CONTACT_NOTE,
      action: 'server_contact',
    }
  }
  return {
    headline: 'This browser is subscribed',
    detail: DELIVERY_NOTE,
    action: 'none',
  }
}
