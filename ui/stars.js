/* ==========================================================================
   TrustMeBro — Bundui Interactive Dynamics Stars Background Engine
   Vanilla JS implementation matching @bundui/components/stars
   ========================================================================== */

(function initStarsBackground() {
  function generateStars(count, colorPrimary, colorAccent) {
    const stars = [];
    for (let i = 0; i < count; i++) {
      const x = Math.floor(Math.random() * 4000) - 2000;
      const y = Math.floor(Math.random() * 4000) - 2000;
      // 15% stars with warm gold accent matching TrustMeBro palette
      const color = (i % 7 === 0 && colorAccent) ? colorAccent : colorPrimary;
      stars.push(x + "px " + y + "px " + color);
    }
    return stars.join(", ");
  }

  function getThemeColors() {
    const isLight = document.documentElement.dataset.theme === "light";
    if (isLight) {
      return {
        primary: "rgba(100, 125, 155, 0.75)",
        accent: "rgba(180, 140, 65, 0.9)"
      };
    } else {
      return {
        primary: "rgba(255, 255, 255, 0.9)",
        accent: "rgba(255, 215, 115, 0.95)"
      };
    }
  }

  function setup() {
    // Find or create the background root container
    let root = document.getElementById("stars-bg") || document.getElementById("nebula-bg");
    if (!root) {
      root = document.createElement("div");
      root.id = "stars-bg";
      root.className = "stars-bg";
      root.setAttribute("aria-hidden", "true");
      document.body.prepend(root);
    } else {
      root.className = "stars-bg";
    }

    // Build the parallax and star layers DOM
    root.innerHTML = `
      <div class="stars-parallax-container" id="stars-parallax">
        <div class="star-layer star-layer-1" data-slot="star-layer-1">
          <div class="star-tile-1" id="star-tile-1a" style="width:1px;height:1px;"></div>
          <div class="star-tile-2" id="star-tile-1b" style="width:1px;height:1px;"></div>
        </div>
        <div class="star-layer star-layer-2" data-slot="star-layer-2">
          <div class="star-tile-1" id="star-tile-2a" style="width:2px;height:2px;"></div>
          <div class="star-tile-2" id="star-tile-2b" style="width:2px;height:2px;"></div>
        </div>
        <div class="star-layer star-layer-3" data-slot="star-layer-3">
          <div class="star-tile-1" id="star-tile-3a" style="width:3px;height:3px;"></div>
          <div class="star-tile-2" id="star-tile-3b" style="width:3px;height:3px;"></div>
        </div>
      </div>
      <div class="stars-vignette"></div>
    `;

    const parallaxEl = document.getElementById("stars-parallax");
    const tile1a = document.getElementById("star-tile-1a");
    const tile1b = document.getElementById("star-tile-1b");
    const tile2a = document.getElementById("star-tile-2a");
    const tile2b = document.getElementById("star-tile-2b");
    const tile3a = document.getElementById("star-tile-3a");
    const tile3b = document.getElementById("star-tile-3b");

    function updateStarShadows() {
      const colors = getThemeColors();
      const shadow1 = generateStars(1000, colors.primary, colors.accent);
      const shadow2 = generateStars(400, colors.primary, colors.accent);
      const shadow3 = generateStars(200, colors.primary, colors.accent);

      if (tile1a && tile1b) {
        tile1a.style.boxShadow = shadow1;
        tile1b.style.boxShadow = shadow1;
      }
      if (tile2a && tile2b) {
        tile2a.style.boxShadow = shadow2;
        tile2b.style.boxShadow = shadow2;
      }
      if (tile3a && tile3b) {
        tile3a.style.boxShadow = shadow3;
        tile3b.style.boxShadow = shadow3;
      }
    }

    updateStarShadows();

    // Theme mutation observer to update star colors on theme toggle
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "attributes" && m.attributeName === "data-theme") {
          updateStarShadows();
          break;
        }
      }
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    // Interactive mouse spring parallax physics (matching Framer Motion spring)
    const factor = 0.05;
    const stiffness = 50;
    const damping = 20;

    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let velX = 0;
    let velY = 0;
    let lastTime = performance.now();
    let animId = null;
    let isMoving = false;

    function handleMouseMove(e) {
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      targetX = -(e.clientX - centerX) * factor;
      targetY = -(e.clientY - centerY) * factor;
      if (!isMoving) {
        isMoving = true;
        lastTime = performance.now();
        animId = requestAnimationFrame(animateSpring);
      }
    }

    function animateSpring(now) {
      const dt = Math.min((now - lastTime) / 1000, 0.064);
      lastTime = now;

      // Spring-damper differential equations
      const forceX = stiffness * (targetX - currentX) - damping * velX;
      const forceY = stiffness * (targetY - currentY) - damping * velY;

      velX += forceX * dt;
      velY += forceY * dt;

      currentX += velX * dt;
      currentY += velY * dt;

      if (parallaxEl) {
        parallaxEl.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`;
      }

      // Check settling condition
      if (
        Math.abs(targetX - currentX) < 0.05 &&
        Math.abs(targetY - currentY) < 0.05 &&
        Math.abs(velX) < 0.05 &&
        Math.abs(velY) < 0.05
      ) {
        currentX = targetX;
        currentY = targetY;
        velX = 0;
        velY = 0;
        if (parallaxEl) {
          parallaxEl.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`;
        }
        isMoving = false;
        animId = null;
        return;
      }

      animId = requestAnimationFrame(animateSpring);
    }

    window.addEventListener("pointermove", handleMouseMove, { passive: true });

    // Handle visibility changes
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && animId) {
        cancelAnimationFrame(animId);
        animId = null;
        isMoving = false;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
