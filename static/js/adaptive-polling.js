(function () {
  function createPoller({
    poll,
    getDelay,
    errorDelay = 10000,
    onError = null,
    autoStart = true,
    pollWhileHidden = false,
  }) {
    let timer = null;
    let stopped = true;
    let running = false;

    const clearTimer = () => {
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
      }
    };

    const schedule = (delay) => {
      clearTimer();
      if (stopped || (document.hidden && !pollWhileHidden)) {
        return;
      }
      const safeDelay = Number.isFinite(delay) && delay > 0 ? delay : errorDelay;
      timer = window.setTimeout(run, safeDelay);
    };

    const run = async () => {
      if (running) {
        return;
      }

      running = true;
      try {
        const result = await poll();
        schedule(getDelay(result));
      } catch (error) {
        if (onError) {
          onError(error);
        }
        schedule(errorDelay);
      } finally {
        running = false;
      }
    };

    const start = (initialDelay = null) => {
      stopped = false;
      if (typeof initialDelay === "number") {
        schedule(initialDelay);
      } else {
        run();
      }
    };

    const stop = () => {
      stopped = true;
      clearTimer();
    };

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        if (!pollWhileHidden) {
          clearTimer();
        }
      } else if (!stopped) {
        run();
      }
    });

    if (autoStart) {
      start();
    }

    return {
      start,
      stop,
      run,
      schedule,
    };
  }

  window.ServeAdaptivePolling = {
    createPoller,
  };
})();
