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

  const fundCoordinator = async () => {
    if (!coordinatorAddress || !window.kasware) return;
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
    <div style={styles.container}>
      <div style={styles.header}>💰 Wallet</div>

      {/* Coordinator Balance — always visible */}
      <div style={styles.row}>
        <span style={styles.label}>Coordinator:</span>
        <span style={{...styles.value, color: '#ffaa00'}}>
          {coordinatorBalance !== null ? `${coordinatorBalance} KAS` : '...'}
        </span>
      </div>

      {!walletAddress ? (
        <button onClick={connectWallet} style={styles.connectButton}>
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

          <button 
            onClick={fundCoordinator} 
            disabled={isFunding || !coordinatorAddress}
            style={{...styles.fundButton, opacity: isFunding ? 0.7 : 1}}
          >
            {isFunding ? '⏳ Sending...' : '💸 Fund Coordinator (50 KAS)'}
          </button>
        </div>
      )}

      {status && <div style={styles.status}>{status}</div>}
    </div>
  );
};

const styles = {
  container: {
    position: 'absolute',
    top: '20px',
    right: '390px',
    zIndex: 1001,
    background: 'rgba(10, 10, 10, 0.9)',
    backdropFilter: 'blur(10px)',
    borderRadius: '12px',
    padding: '12px 14px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    width: '230px',
    color: '#fff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '12px',
  },
  header: {
    fontSize: '13px',
    fontWeight: 'bold',
    marginBottom: '8px',
    color: '#fff',
  },
  connectButton: {
    background: 'linear-gradient(135deg, #00ff88, #00cc6a)',
    color: '#000',
    border: 'none',
    padding: '8px 14px',
    borderRadius: '8px',
    fontWeight: 'bold',
    cursor: 'pointer',
    width: '100%',
    fontSize: '12px',
    marginTop: '6px',
  },
  walletInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '11px',
    marginBottom: '2px',
  },
  label: {
    color: '#888',
  },
  value: {
    color: '#00ff88',
    fontWeight: 'bold',
  },
  fundButton: {
    background: 'linear-gradient(135deg, #00ff88, #00cc6a)',
    color: '#000',
    border: 'none',
    padding: '8px',
    borderRadius: '8px',
    fontWeight: 'bold',
    cursor: 'pointer',
    marginTop: '4px',
    fontSize: '11px',
  },
  status: {
    fontSize: '10px',
    color: '#aaa',
    marginTop: '6px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: '210px',
  },
};

export default WalletConnect;
