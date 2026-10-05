package com.ishland.c2me.base.common.util;

public class BooleanUtils {

    public static boolean parseBoolean(String value) {
        if ("true".equalsIgnoreCase(value)) return true;
        if ("false".equalsIgnoreCase(value)) return false;
        throw new BooleanFormatException(value);
    }

    public static class BooleanFormatException extends RuntimeException {
        public BooleanFormatException() {
            super();
        }

        public BooleanFormatException(String message) {
            super(message);
        }

        public BooleanFormatException(String message, Throwable exception) {
            super(message, exception);
        }

        public BooleanFormatException(Throwable exception) {
            super(exception);
        }

        protected BooleanFormatException(String message, Throwable exception, boolean enableSuppression, boolean writableStackTrace) {
            super(message, exception, enableSuppression, writableStackTrace);
        }
    }

}
