export function DashboardContentSkeleton() {
  return (
    <div className="dashboard-content-skeleton">
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <div className="skeleton-shimmer" style={{ width: 140, height: 12, marginBottom: 8 }} />
          <div className="skeleton-shimmer" style={{ width: 240, height: 26, marginBottom: 8 }} />
          <div className="skeleton-shimmer" style={{ width: 360, height: 14 }} />
        </div>
        <div className="actions" style={{ display: 'flex', gap: 8 }}>
          <div className="skeleton-shimmer" style={{ width: 115, height: 38, borderRadius: 8 }} />
          <div className="skeleton-shimmer" style={{ width: 115, height: 38, borderRadius: 8 }} />
        </div>
      </div>

      {/* Overview Banner */}
      <div className="overview-banner">
        <div className="banner-icon skeleton-shimmer" style={{ width: 42, height: 42, borderRadius: 10 }} />
        <div style={{ flex: 1 }}>
          <div className="skeleton-shimmer" style={{ width: 260, height: 15, marginBottom: 6 }} />
          <div className="skeleton-shimmer" style={{ width: 400, height: 13 }} />
        </div>
        <div className="banner-date">
          <div className="skeleton-shimmer" style={{ width: 95, height: 12 }} />
        </div>
      </div>

      {/* Stats Grid: 4 cards matching .stats-grid */}
      <div className="stats-grid">
        {[1, 2, 3, 4].map(idx => (
          <div key={idx} className="stat-card">
            <div className="stat-top">
              <div className="skeleton-shimmer" style={{ width: 95, height: 13 }} />
              <div className="skeleton-shimmer" style={{ width: 28, height: 28, borderRadius: 8 }} />
            </div>
            <div className="stat-value">
              <div className="skeleton-shimmer" style={{ width: 105, height: 30, margin: '10px 0 12px' }} />
            </div>
            <div className="stat-detail">
              <div className="skeleton-shimmer" style={{ width: 140, height: 12 }} />
            </div>
          </div>
        ))}
      </div>

      {/* Dashboard Charts: 2 panels matching .dashboard-charts */}
      <div className="dashboard-charts">
        {/* Left: Chart panel */}
        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="skeleton-shimmer" style={{ width: 150, height: 15, marginBottom: 6 }} />
              <div className="skeleton-shimmer" style={{ width: 240, height: 13 }} />
            </div>
            <div className="skeleton-shimmer" style={{ width: 65, height: 14, borderRadius: 4 }} />
          </div>
          <div className="chart-container" style={{ display: 'flex', alignItems: 'flex-end', gap: 14, padding: '24px 20px 10px' }}>
            {[40, 65, 50, 85, 60, 95, 75, 90, 70, 80].map((h, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: '100%', justifyContent: 'flex-end' }}>
                <div className="skeleton-shimmer" style={{ width: '100%', height: `${h}%`, borderRadius: '6px 6px 0 0', opacity: 0.85 }} />
                <div className="skeleton-shimmer" style={{ width: 26, height: 10 }} />
              </div>
            ))}
          </div>
          <div className="chart-bottom">
            <div className="skeleton-shimmer" style={{ width: 150, height: 12 }} />
            <div className="skeleton-shimmer" style={{ width: 110, height: 12 }} />
          </div>
        </section>

        {/* Right: Action centre panel */}
        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="skeleton-shimmer" style={{ width: 110, height: 15, marginBottom: 6 }} />
              <div className="skeleton-shimmer" style={{ width: 160, height: 13 }} />
            </div>
          </div>
          <div className="action-list">
            {[1, 2, 3].map(item => (
              <div key={item} className="action-item">
                <div className="skeleton-shimmer" style={{ width: 38, height: 38, borderRadius: 9 }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton-shimmer" style={{ width: 140, height: 13, marginBottom: 5 }} />
                  <div className="skeleton-shimmer" style={{ width: 170, height: 12 }} />
                </div>
                <div className="skeleton-shimmer" style={{ width: 24, height: 18 }} />
              </div>
            ))}
          </div>
          <div className="confirmation-summary">
            <div className="skeleton-shimmer" style={{ width: 22, height: 22, borderRadius: 4 }} />
            <div style={{ flex: 1 }}>
              <div className="skeleton-shimmer" style={{ width: 160, height: 13, marginBottom: 4 }} />
              <div className="skeleton-shimmer" style={{ width: 190, height: 11 }} />
            </div>
          </div>
        </section>
      </div>

      {/* Recent Deposit Records Panel */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="skeleton-shimmer" style={{ width: 160, height: 15, marginBottom: 6 }} />
            <div className="skeleton-shimmer" style={{ width: 280, height: 13 }} />
          </div>
          <div className="skeleton-shimmer" style={{ width: 115, height: 14, borderRadius: 4 }} />
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {['Deposit / institution', 'Deposit value', 'Maturity date', 'Verification', 'Case status', 'Actions'].map((h, i) => (
                  <th key={i}>
                    <div className="skeleton-shimmer" style={{ width: i === 5 ? 20 : 95, height: 12 }} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[1, 2, 3, 4, 5].map(row => (
                <tr key={row}>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 110, height: 13, marginBottom: 5 }} />
                    <div className="skeleton-shimmer" style={{ width: 150, height: 11 }} />
                  </td>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 90, height: 13, marginBottom: 5 }} />
                    <div className="skeleton-shimmer" style={{ width: 120, height: 11 }} />
                  </td>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 85, height: 13, marginBottom: 5 }} />
                    <div className="skeleton-shimmer" style={{ width: 100, height: 11 }} />
                  </td>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 80, height: 22, borderRadius: 6 }} />
                  </td>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 70, height: 22, borderRadius: 6 }} />
                  </td>
                  <td>
                    <div className="skeleton-shimmer" style={{ width: 20, height: 20, borderRadius: 4 }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

export function DashboardSkeleton({ portal = 'institute' }: { portal?: 'institute' | 'admin' }) {
  return (
    <div className="app-shell dashboard-skeleton-shell" data-portal={portal}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="skeleton-shimmer" style={{ width: 28, height: 28, borderRadius: 6 }} />
            <div className="skeleton-shimmer" style={{ width: 105, height: 16 }} />
          </div>
        </div>

        <div className="workspace-card">
          <div className="skeleton-shimmer" style={{ width: 31, height: 31, borderRadius: 6 }} />
          <div style={{ flex: 1 }}>
            <div className="skeleton-shimmer" style={{ width: '80%', height: 11, marginBottom: 5 }} />
            <div className="skeleton-shimmer" style={{ width: '55%', height: 9 }} />
          </div>
        </div>

        <nav>
          <div className="nav-group">
            <div className="skeleton-shimmer" style={{ width: 60, height: 9, margin: '0 0.8125rem 0.75rem' }} />
            {[105, 85, 120, 95, 110].map((w, idx) => (
              <div key={idx} className="nav-link" style={{ pointerEvents: 'none' }}>
                <div className="skeleton-shimmer" style={{ width: 16, height: 16, borderRadius: 4 }} />
                <div className="skeleton-shimmer" style={{ width: w, height: 11 }} />
              </div>
            ))}
          </div>
          <div className="nav-group">
            <div className="skeleton-shimmer" style={{ width: 50, height: 9, margin: '0 0.8125rem 0.75rem' }} />
            {[90, 115].map((w, idx) => (
              <div key={idx} className="nav-link" style={{ pointerEvents: 'none' }}>
                <div className="skeleton-shimmer" style={{ width: 16, height: 16, borderRadius: 4 }} />
                <div className="skeleton-shimmer" style={{ width: w, height: 11 }} />
              </div>
            ))}
          </div>
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card" style={{ opacity: 0.8 }}>
            <div className="skeleton-shimmer" style={{ width: 22, height: 22, borderRadius: 4, marginBottom: 8 }} />
            <div className="skeleton-shimmer" style={{ width: '70%', height: 11, marginBottom: 6 }} />
            <div className="skeleton-shimmer" style={{ width: '90%', height: 9, marginBottom: 4 }} />
            <div className="skeleton-shimmer" style={{ width: '60%', height: 9 }} />
          </div>
          <div className="nav-link" style={{ pointerEvents: 'none' }}>
            <div className="skeleton-shimmer" style={{ width: 16, height: 16, borderRadius: 4 }} />
            <div className="skeleton-shimmer" style={{ width: 65, height: 11 }} />
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="skeleton-shimmer" style={{ width: 70, height: 20, borderRadius: 4 }} />
            <span style={{ color: 'var(--text-neutral-71)' }}>/</span>
            <div className="skeleton-shimmer" style={{ width: 110, height: 14 }} />
          </div>

          <div style={{ flex: 1, maxWidth: 360, margin: '0 1.5rem' }}>
            <div className="skeleton-shimmer" style={{ width: '100%', height: 34, borderRadius: 6 }} />
          </div>

          <div className="topbar-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <div className="skeleton-shimmer" style={{ width: 90, height: 28, borderRadius: 14 }} />
            <div className="skeleton-shimmer" style={{ width: 30, height: 30, borderRadius: 6 }} />
            <div className="topbar-divider" />
            <div className="skeleton-shimmer" style={{ width: 32, height: 32, borderRadius: '50%' }} />
          </div>
        </header>

        <main className="page-content">
          <DashboardContentSkeleton />
        </main>

        <footer className="page-footer">
          <div className="skeleton-shimmer" style={{ width: 240, height: 11 }} />
          <div className="skeleton-shimmer" style={{ width: 180, height: 11 }} />
        </footer>
      </div>
    </div>
  )
}
