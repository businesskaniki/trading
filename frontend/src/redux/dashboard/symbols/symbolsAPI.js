import api from "../../../api/axios";

const symbolsAPI = {
  /**
   * Synchronize the selected trading account's symbols
   * from the MT5 bridge.
   */
  syncSymbols: async (accountId) => {
    const response = await api.post(
      `/trading-accounts/${accountId}/symbols/sync`,
    );

    return response.data;
  },

  /**
   * Fetch all symbols synchronized for a trading account.
   */
  getAccountSymbols: async (accountId) => {
    const response = await api.get(`/trading-accounts/${accountId}/symbols/`);

    return response.data;
  },

  /**
   * Fetch only the symbols currently enabled for trading.
   */
  getTradingUniverse: async (accountId) => {
    const response = await api.get(
      `/trading-accounts/${accountId}/symbols/universe`,
    );

    return response.data;
  },

  /**
   * Enable or disable a symbol for the trading account.
   */
  setSymbolSelection: async (accountId, accountSymbolId, enabled) => {
    const response = await api.patch(
      `/trading-accounts/${accountId}/symbols/${accountSymbolId}/selection`,
      {
        enabled,
      },
    );

    return response.data;
  },
};

export default symbolsAPI;
