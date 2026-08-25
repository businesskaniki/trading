import Cookies from "js-cookie";

export const setCookie = (name, value, options = {}) =>
  Cookies.set(name, value, { sameSite: "lax", secure: true, ...options });

export const getCookie = (name) => Cookies.get(name);

export const removeCookie = (name) => Cookies.remove(name);
