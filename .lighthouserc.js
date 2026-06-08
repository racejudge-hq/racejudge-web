module.exports = {
  ci: {
    collect: {
      url: ["http://localhost:3000/", "http://localhost:3000/decisions", "http://localhost:3000/predict"],
      startServerCommand: "npm run start",
      startServerReadyPattern: "ready on",
      startServerReadyTimeout: 30000,
      numberOfRuns: 2,
      settings: {
        chromeFlags: "--no-sandbox --disable-dev-shm-usage",
      },
    },
    assert: {
      assertions: {
        "categories:performance":    ["warn",  { minScore: 0.90 }],
        "categories:accessibility":  ["error", { minScore: 0.95 }],
        "categories:best-practices": ["warn",  { minScore: 0.90 }],
        "categories:seo":            ["warn",  { minScore: 0.90 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
