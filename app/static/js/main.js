// Shared site behavior: mobile nav toggle, FAQ accordion, navbar scroll shadow,
// scroll-reveal animations, and interactive WhatsApp demo mockup.
(function () {
  // Mobile Nav Toggle
  const toggle = document.getElementById("navToggle");
  const links = document.getElementById("navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", () => {
      const isOpen = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
    links.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        links.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // FAQ Accordion
  document.querySelectorAll(".faq-item").forEach((item) => {
    const question = item.querySelector(".faq-question");
    if (!question) return;
    question.addEventListener("click", () => {
      const isOpen = item.classList.contains("is-open");
      document.querySelectorAll(".faq-item.is-open").forEach((open) => {
        if (open !== item) open.classList.remove("is-open");
      });
      item.classList.toggle("is-open", !isOpen);
    });
  });

  // Navbar Scroll Shadow
  const navbar = document.getElementById("siteNavbar");
  if (navbar) {
    const onScroll = () => {
      navbar.classList.toggle("is-scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Scroll Reveal Observer
  const revealTargets = document.querySelectorAll(".reveal");
  if (revealTargets.length) {
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (prefersReducedMotion || !("IntersectionObserver" in window)) {
      revealTargets.forEach((el) => el.classList.add("is-visible"));
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
      );
      revealTargets.forEach((el) => observer.observe(el));
    }
  }

  // Interactive WhatsApp Demo Simulator
  const demoData = {
    briefing: [
      {
        type: "in",
        content: "Good Morning ☀️\n\n<strong>Receivable Today</strong>\n<span class=\"wa-figure\">₹92,000</span>\n\n<strong>Supplier Due</strong>\n<span class=\"wa-figure\">₹40,000</span>\n\n<strong>Expected Cash</strong>\n<span class=\"wa-figure\">₹2,84,000</span>"
      }
    ],
    outstanding: [
      {
        type: "out",
        content: "2"
      },
      {
        type: "in",
        content: "<strong>Outstanding Report</strong>\n\nSiddha Mahaveer Agencies\n<span class=\"wa-figure\">₹3,19,828</span> · High risk\n\nReliable Medical\n<span class=\"wa-figure\">₹39,986</span> · High risk"
      }
    ],
    cash: [
      {
        type: "out",
        content: "Cash position?"
      },
      {
        type: "in",
        content: "<strong>Cash Position</strong>\n\nAvailable today: <span class=\"wa-figure\">₹2,41,000</span>\nAfter Friday's dues: <span class=\"wa-figure\">₹1,58,000</span>\n\nSuggested: delay ABC Foods payment by one day."
      }
    ]
  };

  const phoneBody = document.getElementById("demoPhoneBody");
  const tabButtons = document.querySelectorAll(".demo-tab-btn");
  let activeDemoTimeout = null;

  function runDemoSequence(key) {
    if (!phoneBody) return;
    
    // Clear any active sequence
    if (activeDemoTimeout) clearTimeout(activeDemoTimeout);
    phoneBody.innerHTML = "";

    const sequence = demoData[key];
    if (!sequence) return;

    let index = 0;

    function nextBubble() {
      if (index >= sequence.length) return;
      const data = sequence[index];
      
      // Simulate typing indicator
      const typingBubble = document.createElement("div");
      typingBubble.className = `wa-bubble ${data.type === 'out' ? 'wa-out' : ''}`;
      typingBubble.style.opacity = "0.75";
      typingBubble.innerHTML = `<span style="font-style: italic; color: var(--ink-soft)">typing...</span>`;
      phoneBody.appendChild(typingBubble);
      phoneBody.scrollTop = phoneBody.scrollHeight;

      activeDemoTimeout = setTimeout(() => {
        // Remove typing indicator and show real bubble
        if (phoneBody.contains(typingBubble)) {
          phoneBody.removeChild(typingBubble);
        }

        const realBubble = document.createElement("div");
        realBubble.className = `wa-bubble ${data.type === 'out' ? 'wa-out' : ''}`;
        realBubble.innerHTML = data.content.replace(/\n/g, "<br>");
        phoneBody.appendChild(realBubble);
        phoneBody.scrollTop = phoneBody.scrollHeight;

        index++;
        activeDemoTimeout = setTimeout(nextBubble, 1200);
      }, 700);
    }

    nextBubble();
  }

  // Tab click handler
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.classList.contains("is-active")) return;
      
      tabButtons.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");

      const demoKey = btn.getAttribute("data-demo");
      runDemoSequence(demoKey);
    });
  });

  // Run default on page load
  if (phoneBody && tabButtons.length) {
    runDemoSequence("briefing");
  }

  // Wake-and-redirect: links marked data-wake-redirect point at the Render
  // backend, which spins down after 15 minutes idle and would otherwise show
  // Render's own cold-start splash on the next visit. We cover that with our
  // own branded loader and only hand off once the backend answers (or after
  // a max wait, so a real outage doesn't strand the user here forever).
  const WAKE_POLL_MS = 2500;
  const WAKE_MAX_WAIT_MS = 45000;
  const WAKE_MESSAGES = [
    "Waking up your WhatsApp assistant…",
    "Just a moment — this only happens after a quiet spell.",
    "Almost there, spinning up the servers…",
    "Thanks for your patience, hang tight…",
  ];

  function pingAwake(url) {
    // no-cors: we can't read the response, but the promise resolving at all
    // (even with an opaque result) means something answered — enough to know
    // it's safe to navigate. Rejects on real network failure.
    return fetch(url, { mode: "no-cors", cache: "no-store" }).then(
      () => true,
      () => false
    );
  }

  function showWakeOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "wake-overlay";
    overlay.innerHTML =
      '<div class="orb orb-green" style="top: 10%; left: -150px; width: 400px; height: 400px;"></div>' +
      '<div class="orb orb-mint" style="bottom: 5%; right: -150px; width: 400px; height: 400px;"></div>' +
      '<div class="wake-card">' +
      '<div class="wake-spinner"></div>' +
      "<h2>Getting things ready</h2>" +
      '<p class="wake-message">' + WAKE_MESSAGES[0] + "</p>" +
      "</div>";
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("is-visible"));
    return overlay;
  }

  async function wakeAndGo(targetUrl, healthUrl) {
    const overlay = showWakeOverlay();
    const messageEl = overlay.querySelector(".wake-message");
    let messageIndex = 0;
    const messageTimer = setInterval(() => {
      messageIndex = (messageIndex + 1) % WAKE_MESSAGES.length;
      messageEl.textContent = WAKE_MESSAGES[messageIndex];
    }, 4000);

    const deadline = Date.now() + WAKE_MAX_WAIT_MS;
    let awake = await pingAwake(healthUrl);
    while (!awake && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, WAKE_POLL_MS));
      awake = await pingAwake(healthUrl);
    }
    clearInterval(messageTimer);
    window.location.href = targetUrl;
  }

  document.querySelectorAll("[data-wake-redirect]").forEach((link) => {
    // Only intercept when the link actually leaves this origin (i.e. the
    // static Vercel site pointing at the Render backend). A same-origin
    // relative link means the page already loaded from a warm backend, so
    // there's nothing to wake.
    let isCrossOrigin = false;
    try {
      isCrossOrigin = new URL(link.href, window.location.href).origin !== window.location.origin;
    } catch (err) {
      isCrossOrigin = false;
    }
    if (!isCrossOrigin) return;

    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = new URL(link.href, window.location.href);
      wakeAndGo(target.href, `${target.origin}/health`);
    });
  });
})();
