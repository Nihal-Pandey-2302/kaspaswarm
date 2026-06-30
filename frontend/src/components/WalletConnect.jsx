import React, { useState, useEffect } from 'react';
import { API_BASE } from '../utils/config';

const WalletConnect = () => {
  const [walletAddress, setWalletAddress] = useState(null);
  const [coordinatorAddress, setCoordinatorAddress] = useState(null);
  const [coordinatorBalance, setCoordinatorBalance] = useState(null);
  const [balance, setBalance] = useState(null);
  const [status, setStatus] = useState('');
  const [isFunding, setIsFunding] = useState(false);
  const [isWalletDetected, setIsWalletDetected] = useState(false);

  // Fetch Coordinator Address on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/address`)
      .then(res => res.json())
      .then(data => setCoordinatorAddress(data.address))
      .catch(err => console.error("Failed to fetch coordinator address:", err));
  }, []);

  // Fetch coordinator balance periodically
  useEffect(() => {
    const fetchBalance = () => {
      fetch(`${API_BASE}/api/coordinator-balance`)
        .then(res => res.json())
        .then(data => setCoordinatorBalance(data.balance_kas))
        .catch(() => {});
    };
    fetchBalance();
    const interval = setInterval(fetchBalance, 15000);
    return () => clearInterval(interval);
  }, []);

  // Poll for wallet injection
  useEffect(() => {
    const checkWallet = () => {
      if (window.kasware) {
        setIsWalletDetected(true);
        setStatus('');
        return true;
      }
      return false;
    };
    if (checkWallet()) return;
    const interval = setInterval(() => {
      if (checkWallet()) clearInterval(interval);
    }, 500);
    const timeout = setTimeout(() => {
      clearInterval(interval);
      if (!window.kasware) setStatus('Wallet not detected.');
    }, 5000);
    return () => { clearInterval(interval); clearTimeout(timeout); };
  }, []);

  const connectWallet = async () => {
    if (!window.kasware) {
      if (confirm("KasWare Wallet not detected. Open download page?")) {
        window.open('https://www.kasware.xyz/', '_blank');
      }
      return;
    }
    try {
      const accounts = await window.kasware.requestAccounts();
      if (accounts && accounts.length > 0) {
        setWalletAddress(accounts[0]);
        const bal = await window.kasware.getBalance();
        setBalance(bal.total / 100000000);
        setStatus('');
      }
    } catch (err) {
      setStatus("Connection failed: " + err.message);
    }
  };

  const validCoord = !!coordinatorAddress && coordinatorAddress.startsWith('kaspatest:');
  const isSelf = !!walletAddress && walletAddress === coordinatorAddress;

  const fundCoordinator = async () => {
    if (!validCoord || !window.kasware) {
      setStatus('⚠️ Coordinator address not configured (live mode only)');
      return;
    }
    setIsFunding(true);
    setStatus("Initiating transaction...");
    try {
      const amount = 50 * 100000000; // 50 KAS in Sompi
      const txHash = await window.kasware.sendKaspa(coordinatorAddress, amount);
      setStatus(`✅ Sent! Tx: ${txHash.slice(0, 12)}...`);
      // Refresh balances
      setTimeout(async () => {
        const bal = await window.kasware.getBalance();
        setBalance(bal.total / 100000000);
        // Also refresh coordinator balance
        fetch(`${API_BASE}/api/coordinator-balance`)
          .then(res => res.json())
          .then(data => setCoordinatorBalance(data.balance_kas))
          .catch(() => {});
      }, 5000);
    } catch (err) {
      setStatus("❌ " + err.message);
    } finally {
      setIsFunding(false);
    }
  };

  return (
    <div style={styles.container} className="ks-card">
      <div style={styles.header}>💰 Wallet</div>

      {/* Coordinator Balance — always visible */}
      <div style={styles.row}>
        <span style={styles.label}>Coordinator:</span>
        <span style={{...styles.value, color: '#ffaa00'}}>
          {coordinatorBalance !== null ? `${coordinatorBalance} KAS` : '...'}
        </span>
      </div>

      {!walletAddress ? (
        <button onClick={connectWallet} className="ks-btn" style={styles.connectButton}>
          🔌 Connect KasWare
        </button>
      ) : (
        <div style={styles.walletInfo}>
          <div style={styles.row}>
            <span style={styles.label}>Your Wallet:</span>
            <span style={styles.value}>{walletAddress.slice(0, 12)}...{walletAddress.slice(-4)}</span>
          </div>
          <div style={styles.row}>
            <span style={styles.label}>Your Balance:</span>
            <span style={styles.value}>{balance !== null ? balance.toFixed(2) : '...'} KAS</span>
          </div>

          {isSelf ? (
            <div style={styles.selfNote}>✓ This wallet is the coordinator — no funding needed.</div>
          ) : (
            <button
              onClick={fundCoordinator}
              disabled={isFunding || !validCoord}
              className="ks-btn"
              style={{...styles.fundButton, opacity: (isFunding || !validCoord) ? 0.5 : 1, cursor: validCoord ? 'pointer' : 'not-allowed'}}
              title={validCoord ? '' : 'Coordinator address not configured (live mode only)'}
            >
              {isFunding ? '⏳ Sending...' : '💸 Fund Coordinator (50 KAS)'}
            </button>
          )}
        </div>
      )}

      {status && <div style={styles.status}>{status}</div>}
    </div>
  );
};

const styles = {
  container: {
    background: 'rgba(17, 19, 24, 0.92)',
    backdropFilter: 'blur(12px)',
    borderRadius: '14px',
    padding: '16px',
    border: '1px solid rgba(255, 255, 255, 0.10)',
    width: '100%',
    color: '#f3f5f8',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '12px',
    boxSizing: 'border-box',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
  },
  header: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '1px',
    textTransform: 'uppercase',
    marginBottom: '12px',
    color: '#7d8794',
  },
  connectButton: {
    background: 'linear-gradient(135deg, #00ff88, #00cc6a)',
    color: '#06140d',
    border: 'none',
    padding: '10px 14px',
    borderRadius: '10px',
    fontWeight: 600,
    cursor: 'pointer',
    width: '100%',
    fontSize: '13px',
    marginTop: '8px',
    boxShadow: '0 2px 12px rgba(0, 255, 136, 0.25)',
  },
  walletInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '12px',
    marginBottom: '2px',
  },
  label: {
    color: '#9aa4b2',
    fontWeight: 500,
  },
  value: {
    color: '#00ff88',
    fontWeight: 700,
    fontVariantNumeric: 'tabular-nums',
  },
  fundButton: {
    background: 'linear-gradient(135deg, #00ff88, #00cc6a)',
    color: '#06140d',
    border: 'none',
    padding: '10px',
    borderRadius: '10px',
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: '6px',
    fontSize: '12px',
    boxShadow: '0 2px 12px rgba(0, 255, 136, 0.25)',
  },
  selfNote: {
    fontSize: '11px',
    color: '#00ff88',
    background: 'rgba(0,255,136,0.10)',
    border: '1px solid rgba(0,255,136,0.2)',
    borderRadius: '8px',
    padding: '8px 10px',
    marginTop: '6px',
    lineHeight: 1.4,
  },
  status: {
    fontSize: '11px',
    color: '#9aa4b2',
    marginTop: '10px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: '210px',
  },
};

export default WalletConnect;
