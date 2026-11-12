import { useEffect, useMemo, useState } from "react";
import { FaExchangeAlt, FaSearch, FaSyncAlt } from "react-icons/fa";
import { useDispatch, useSelector } from "react-redux";

import {
  fetchPositions,
  syncPositions,
} from "../../../redux/dashboard/positions/positionsThunks";

import { fetchAccounts } from "../../../redux/dashboard/accounts/accountsThunks";
import { fetchAccountSymbols } from "../../../redux/dashboard/symbols/symbolsThunks";

import { usePositionWebSocket } from "../../../hooks/usePositionWebSocket";
import { getAccessToken } from "../../../api/axios";
import { openTickStream } from "../../../api/tickStream";

import "../../../css/positions.css";

/**
 * Resolve the account-specific symbol mapping for a position.
 */
const resolveAccountSymbol = (position, symbolsByAccount) => {
  const accountSymbols = symbolsByAccount[String(position.account_id)] || [];

  const positionSymbolId = position.symbol_id;

  if (positionSymbolId == null) {
    return undefined;
  }

  return accountSymbols.find(
    (item) =>
      (item.symbol_id != null &&
        String(item.symbol_id) === String(positionSymbolId)) ||
      (item.symbol?.id != null &&
        String(item.symbol.id) === String(positionSymbolId)),
  );
};

/**
 * Return the canonical market-data symbol.
 *
 * Prefer the application's normalized symbol name over broker_symbol.
 */
const resolveCanonicalSymbol = (position, symbolsByAccount) => {
  const accountSymbol = resolveAccountSymbol(position, symbolsByAccount);

  const symbol =
    accountSymbol?.symbol_name ||
    accountSymbol?.symbol?.name ||
    accountSymbol?.name;

  return typeof symbol === "string" ? symbol.trim() : "";
};

/**
 * Keep only records belonging to the selected trading account.
 */
const belongsToAccount = (record, accountId) =>
  accountId != null &&
  record?.account_id != null &&
  String(record.account_id) === String(accountId);

const Positions = () => {
  const dispatch = useDispatch();

  const {
    positions: reduxPositions = [],
    loading,
    syncing,
    error,
  } = useSelector((state) => state.positions);

  const accounts = useSelector((state) => state.accounts?.accounts || []);

  // The selected account is the source of truth for this page.
  const selectedAccountId = useSelector(
    (state) => state.accounts?.selectedAccount?.id ?? null,
  );

  const symbolsByAccount = useSelector(
    (state) => state.symbols?.symbolsByAccount || {},
  );

  const [query, setQuery] = useState("");
  const [liveTicks, setLiveTicks] = useState({});

  /*
   * Subscribe to position snapshots.
   *
   * The accountId option should also be supported by
   * usePositionWebSocket so it can reset/re-filter snapshots
   * when the selected account changes.
   */
  const {
    positions: livePositions = [],
    status: liveStatus,
    error: liveError,
    lastUpdatedAt,
  } = usePositionWebSocket({
    getAccessToken,
    initialPositions: reduxPositions,
    accountId: selectedAccountId,
    enabled: Boolean(selectedAccountId),
  });

  /*
   * Defence in depth: never display another account's records,
   * even if Redux or the WebSocket temporarily contains a
   * snapshot from a previous selection.
   */
  const positions = useMemo(() => {
    if (!selectedAccountId) {
      return [];
    }

    const source = Array.isArray(livePositions) ? livePositions : [];

    return source.filter((position) =>
      belongsToAccount(position, selectedAccountId),
    );
  }, [livePositions, selectedAccountId]);

  /*
   * Load the account list first. fetchAccounts.fulfilled should
   * establish or preserve state.accounts.selectedAccount.
   */
  useEffect(() => {
    dispatch(fetchAccounts());
  }, [dispatch]);

  /*
   * Whenever the selected account changes, retrieve only that
   * account's positions and symbol mapping.
   *
   * This also runs after the initial account list establishes a
   * selection.
   */
  useEffect(() => {
    if (!selectedAccountId) {
      return;
    }

    dispatch(fetchPositions(selectedAccountId));
    dispatch(fetchAccountSymbols(selectedAccountId));
  }, [dispatch, selectedAccountId]);

  /*
   * Clear cached quotes when the selected account changes.
   * This avoids briefly showing an old quote in the new view.
   */
  useEffect(() => {
    setLiveTicks({});
  }, [selectedAccountId]);

  /*
   * Stable list of normalized symbols represented by the
   * selected account's open positions.
   */

  /*
   * Build stable subscriptions from the selected account's positions.
   * Each subscription is identified by account_id + canonical symbol_id.
   */
  const tickSubscriptionsKey = useMemo(() => {
    const subscriptions = positions
      .map((position) => {
        const accountSymbol = resolveAccountSymbol(position, symbolsByAccount);

        const canonicalSymbol = resolveCanonicalSymbol(
          position,
          symbolsByAccount,
        );

        const accountId = position.account_id;
        const symbolId = accountSymbol?.symbol_id ?? position.symbol_id;

        if (accountId == null || symbolId == null || !canonicalSymbol) {
          return null;
        }

        return {
          accountId: String(accountId),
          symbolId: String(symbolId),
          canonicalSymbol,
        };
      })
      .filter(Boolean);

    const unique = new Map();

    for (const subscription of subscriptions) {
      const key = `${subscription.accountId}:${subscription.symbolId}`;

      unique.set(key, subscription);
    }

    return JSON.stringify(
      [...unique.values()].sort((a, b) => {
        const accountComparison = a.accountId.localeCompare(b.accountId);

        if (accountComparison !== 0) {
          return accountComparison;
        }

        return a.symbolId.localeCompare(b.symbolId);
      }),
    );
  }, [positions, symbolsByAccount]);

  /*
   * Subscribe using account/symbol IDs.
   *
   * The backend resolves the broker symbol for MT5 and uses
   * the canonical symbol for the local tick hub.
   */
  useEffect(() => {
    const subscriptions = JSON.parse(tickSubscriptionsKey);

    if (subscriptions.length === 0) {
      return undefined;
    }

    const streams = subscriptions.map((subscription) =>
      openTickStream(
        subscription.accountId,
        subscription.symbolId,
        (message) => {
          const tick = message?.tick;

          if (!tick) {
            return;
          }

          const symbolKey = String(
            message.symbol || subscription.canonicalSymbol,
          )
            .trim()
            .toUpperCase();

          const bid = Number(tick.bid);
          const ask = Number(tick.ask);

          const validBid = Number.isFinite(bid) && bid > 0;
          const validAsk = Number.isFinite(ask) && ask > 0;

          setLiveTicks((previous) => {
            const previousQuote = previous[symbolKey];

            const nextBid = validBid ? bid : (previousQuote?.bid ?? null);

            const nextAsk = validAsk ? ask : (previousQuote?.ask ?? null);

            if (
              previousQuote &&
              previousQuote.bid === nextBid &&
              previousQuote.ask === nextAsk
            ) {
              return previous;
            }

            return {
              ...previous,
              [symbolKey]: {
                bid: nextBid,
                ask: nextAsk,
              },
            };
          });
        },
        (streamError) => {
          console.warn(
            `Live tick stream failed for ${subscription.canonicalSymbol}:`,
            streamError,
          );
        },
      ),
    );

    return () => {
      streams.forEach((stream) => stream.close());
    };
  }, [tickSubscriptionsKey]);

  /*
   * Subscribe to market ticks for the selected account's
   * open-position symbols.
   *
   * Long positions are marked against bid; short positions
   * are marked against ask.
   */
  useEffect(() => {
    const symbols = tickSymbolsKey.split("|").filter(Boolean);

    if (symbols.length === 0) {
      return undefined;
    }

    const streams = symbols.map((symbol) =>
      openTickStream(
        symbol,
        (message) => {
          const tick = message?.tick;

          if (!tick) {
            return;
          }

          const symbolKey = String(message.symbol || symbol)
            .trim()
            .toUpperCase();

          const bid = Number(tick.bid);
          const ask = Number(tick.ask);

          const validBid = Number.isFinite(bid) && bid > 0;
          const validAsk = Number.isFinite(ask) && ask > 0;

          setLiveTicks((previous) => {
            const previousQuote = previous[symbolKey];

            const nextBid = validBid ? bid : (previousQuote?.bid ?? null);

            const nextAsk = validAsk ? ask : (previousQuote?.ask ?? null);

            // Avoid unnecessary renders if the quote has not changed.
            if (
              previousQuote &&
              previousQuote.bid === nextBid &&
              previousQuote.ask === nextAsk
            ) {
              return previous;
            }

            return {
              ...previous,
              [symbolKey]: {
                bid: nextBid,
                ask: nextAsk,
              },
            };
          });
        },
        (streamError) => {
          console.warn(`Live tick stream failed for ${symbol}:`, streamError);
        },
      ),
    );

    return () => {
      streams.forEach((stream) => stream.close());
    };
  }, [tickSymbolsKey]);

  /*
   * Resolve an account name for display.
   */
  const accountName = (id) => {
    const account = accounts.find((item) => String(item.id) === String(id));

    return (
      account?.account_name ||
      account?.account_number ||
      String(id || "-").slice(0, 8)
    );
  };

  /*
   * Apply the search query to the already account-scoped positions.
   */
  const visiblePositions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return positions.filter((position) => {
      const accountSymbol = resolveAccountSymbol(position, symbolsByAccount);

      const symbol =
        accountSymbol?.symbol_name ||
        accountSymbol?.name ||
        accountSymbol?.symbol?.name ||
        accountSymbol?.broker_symbol ||
        String(position.symbol_id || "-").slice(0, 8);

      const brokerSymbol = accountSymbol?.broker_symbol || "";

      const searchableText = [
        position.strategy,
        symbol,
        brokerSymbol,
        position.ticket,
        position.direction,
        position.comment,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return !normalizedQuery || searchableText.includes(normalizedQuery);
    });
  }, [positions, query, symbolsByAccount]);

  /*
   * Manually synchronize broker state, then reload positions for
   * the selected account only.
   *
   * Note: syncPositions() retains the existing sync endpoint
   * contract. The backend sync endpoint must be account-scoped
   * separately if it currently synchronizes the active broker
   * account without accepting an account_id.
   */
  const handleSync = async () => {
    if (!selectedAccountId || syncing) {
      return;
    }

    try {
      await dispatch(syncPositions()).unwrap();

      await dispatch(fetchPositions(selectedAccountId)).unwrap();

      dispatch(fetchAccountSymbols(selectedAccountId));
    } catch (syncError) {
      console.error("Failed to synchronize positions:", syncError);
    }
  };

  const connectionLabel =
    {
      connected: "CONNECTED",
      connecting: "CONNECTING",
      reconnecting: "RECONNECTING",
      disconnected: "DISCONNECTED",
    }[liveStatus] || "DISCONNECTED";

  return (
    <main className="positions-page">
      {/* HEADER */}
      <header className="positions-header">
        <div>
          <span className="positions-eyebrow">
            LIVE BROKER STATE · {connectionLabel}
            {lastUpdatedAt
              ? ` · ${new Date(lastUpdatedAt).toLocaleTimeString()}`
              : ""}
          </span>

          <h1>Positions</h1>

          <p>
            Monitor open positions, live market prices and broker-reported
            profit or loss.
          </p>
        </div>

        <button
          type="button"
          className="positions-refresh"
          onClick={handleSync}
          disabled={!selectedAccountId || syncing}
        >
          <FaSyncAlt className={syncing ? "positions-spin" : ""} />

          {syncing ? "Syncing..." : "Sync broker"}
        </button>
      </header>

      {/* ERROR */}
      {(liveError || error) && (
        <div className="positions-error">
          {liveError ||
            (typeof error === "string"
              ? error
              : "Unable to load or synchronize broker positions.")}
        </div>
      )}

      {/* TOOLBAR */}
      <section className="positions-toolbar">
        <div className="positions-search">
          <FaSearch />

          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search strategy, symbol or ticket..."
            aria-label="Search positions"
            disabled={!selectedAccountId}
          />
        </div>

        <span>
          {visiblePositions.length} open position
          {visiblePositions.length === 1 ? "" : "s"}
        </span>
      </section>

      {/* POSITIONS TABLE */}
      <section className="positions-table-wrap">
        <table className="positions-table">
          <thead>
            <tr>
              <th>Position</th>
              <th>Instrument</th>
              <th>Account</th>
              <th>Volume</th>
              <th>Entry / Current</th>
              <th>P/L</th>
              <th>Stops</th>
            </tr>
          </thead>

          <tbody>
            {!selectedAccountId && (
              <tr>
                <td colSpan={7} className="positions-empty">
                  <FaExchangeAlt />
                  <strong>No trading account selected</strong>
                  <span>
                    Select a trading account to view its open positions.
                  </span>
                </td>
              </tr>
            )}

            {selectedAccountId && loading && positions.length === 0 && (
              <tr>
                <td colSpan={7} className="positions-empty">
                  <FaSyncAlt className="positions-spin" />
                  <strong>Loading positions...</strong>
                </td>
              </tr>
            )}

            {selectedAccountId && !loading && visiblePositions.length === 0 && (
              <tr>
                <td colSpan={7} className="positions-empty">
                  <FaExchangeAlt />

                  <strong>No broker positions</strong>

                  <span>
                    This account has no open positions, or its positions have
                    not yet been synchronized.
                  </span>
                </td>
              </tr>
            )}

            {visiblePositions.map((position) => {
              const accountSymbol = resolveAccountSymbol(
                position,
                symbolsByAccount,
              );

              const symbol =
                accountSymbol?.symbol_name ||
                accountSymbol?.name ||
                accountSymbol?.symbol?.name ||
                accountSymbol?.broker_symbol ||
                String(position.symbol_id || "-").slice(0, 8);

              const brokerSymbol = accountSymbol?.broker_symbol || "";

              const canonicalSymbol = resolveCanonicalSymbol(
                position,
                symbolsByAccount,
              );

              const liveQuote = canonicalSymbol
                ? liveTicks[canonicalSymbol.toUpperCase()]
                : null;

              const direction = String(position.direction || "")
                .trim()
                .toLowerCase();

              /*
               * Use the closing-side quote when available:
               * BUY/LONG closes at bid; SELL/SHORT closes at ask.
               *
               * Fall back to the last broker-reported current price.
               */
              const liveCurrentPrice = ["buy", "long"].includes(direction)
                ? liveQuote?.bid
                : ["sell", "short"].includes(direction)
                  ? liveQuote?.ask
                  : null;

              const displayedCurrentPrice =
                liveCurrentPrice ?? position.current_price;

              /*
               * Keep floating P/L broker-reported.
               * Do not recalculate it from ticks without validating
               * contract size, conversion and account currency.
               */
              const floatingProfit = Number(position.floating_profit ?? 0);

              return (
                <tr key={position.id || position.ticket}>
                  {/* POSITION */}
                  <td>
                    <strong>#{position.ticket || "—"}</strong>

                    <span>
                      {position.direction || "—"}
                      {" · "}
                      {position.strategy || "Manual"}
                    </span>
                  </td>

                  {/* INSTRUMENT */}
                  <td>
                    <strong>{symbol}</strong>

                    <span>
                      {brokerSymbol || position.comment || "Broker position"}
                    </span>
                  </td>

                  {/* ACCOUNT */}
                  <td>{accountName(position.account_id)}</td>

                  {/* VOLUME */}
                  <td>{position.current_volume ?? position.volume ?? "—"}</td>

                  {/* ENTRY / CURRENT PRICE */}
                  <td>
                    {position.entry_price ?? "—"}
                    {" / "}
                    {displayedCurrentPrice ?? "—"}
                  </td>

                  {/* BROKER-REPORTED FLOATING P/L */}
                  <td className={floatingProfit >= 0 ? "positive" : "negative"}>
                    {position.floating_profit ?? "0"}
                  </td>

                  {/* STOPS */}
                  <td>
                    SL {position.stop_loss ?? "-"}
                    <br />
                    TP {position.take_profit ?? "-"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
};

export default Positions;
