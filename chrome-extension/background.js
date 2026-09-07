const DASHBOARD_PATTERN = "http://127.0.0.1:8765/*";

chrome.runtime.onMessage.addListener((message, sender) => {
  if (
    message?.type !== "reuse-jaw-dashboard-tab" ||
    !sender.tab?.id ||
    !message.url?.startsWith("http://127.0.0.1:8765/")
  ) {
    return;
  }

  reuseDashboardTab(sender.tab.id, message.url);
});

async function reuseDashboardTab(currentTabId, requestedUrl) {
  const dashboardTabs = await chrome.tabs.query({ url: DASHBOARD_PATTERN });
  if (dashboardTabs.length < 2) {
    return;
  }

  const canonicalTab = dashboardTabs
    .filter((tab) => tab.id !== undefined)
    .sort((left, right) => left.id - right.id)[0];

  if (!canonicalTab?.id || canonicalTab.id === currentTabId) {
    return;
  }

  await chrome.tabs.update(canonicalTab.id, {
    active: true,
    url: requestedUrl
  });

  if (canonicalTab.windowId !== undefined) {
    await chrome.windows.update(canonicalTab.windowId, { focused: true });
  }

  await chrome.tabs.remove(currentTabId);
}
