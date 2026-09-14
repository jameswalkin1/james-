(function () {
  var PRICE = window.HS_PRICE || '';
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Put the price inside the Add to cart button, and keep it there if the
     theme re-renders the form after a variant or cart change. */
  function labelPrice() {
    if (!PRICE) return;
    document.querySelectorAll('.add-to-cart-button').forEach(function (btn) {
      if (btn.querySelector('.hs-price-tag')) return;
      if (btn.hasAttribute('disabled')) return;
      var tag = document.createElement('span');
      tag.className = 'hs-price-tag';
      tag.textContent = ' — ' + PRICE;
      btn.appendChild(tag);
    });
  }

  function revealGallery() {
    var els = document.querySelectorAll('media-gallery .product-media-container');
    if (!els.length || reduce || !('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.1 });
    els.forEach(function (el, i) {
      if (i === 0) return;            /* never hide the first image */
      el.classList.add('hs-r');
      io.observe(el);
    });
  }

  function start() {
    labelPrice();
    revealGallery();
    var form = document.querySelector('product-form-component') || document.body;
    if ('MutationObserver' in window) {
      new MutationObserver(labelPrice).observe(form, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else { start(); }
})();
