async function withFixedDateNow(timestamp, action) {
  const originalDateNow = Date.now;
  Date.now = () => timestamp;
  try {
    return await action();
  } finally {
    Date.now = originalDateNow;
  }
}

module.exports = { withFixedDateNow };
