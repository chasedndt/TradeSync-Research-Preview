import { useLocation } from 'react-router-dom'
import { List } from '../icons'
import { HarnessSwitch } from '../harness/HarnessSwitch'
import { OperatorMenu } from './OperatorMenu'
import { PipelineStatusMenu } from './PipelineStatusMenu'
import { WalletConnectMenu } from '../wallet/WalletConnectMenu'

export function Header({ onMenu }: { onMenu: () => void }) {
  const location = useLocation()
  const section = ({
    '/': 'Mission Control',
    '/market': 'Market',
    '/canvas': 'Market Canvas',
    '/intake': 'Knowledge intake',
    '/opportunities': 'Opportunities',
    '/regime-lab': 'Regime Lab',
    '/thesis': 'Thesis',
    '/agents': 'Agents',
    '/fleet': 'Fleet',
    '/pipeline': 'Integration Pipeline',
    '/sources': 'Sources',
    '/logs': 'Activity & Evidence',
    '/execution': 'Execution Readiness',
    '/settings': 'Settings',
  } as Record<string, string>)[location.pathname] || 'TradeSync'

  return (
    <header className="topbar">
      <div className="topbar-title-wrap">
        <button className="mobile-menu" onClick={onMenu} aria-label="Open navigation">
          <List size={22} />
        </button>
        <div className="topbar-page-title">
          <span>TradeSync</span>
          <h1>{section}</h1>
        </div>
      </div>
      <div className="topbar-meta">
        <HarnessSwitch />
        <PipelineStatusMenu />
        <OperatorMenu />
        <WalletConnectMenu />
      </div>
    </header>
  )
}
