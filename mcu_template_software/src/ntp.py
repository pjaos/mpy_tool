import utime
import ntptime

class NTP(object):
    """@brief Responsible for setting the MCU time with time received from an NTP server."""

    NTP_HOST                    = "pool.ntp.org"

    def __init__(self, uo, interval_seconds):
        """@brief Constructor.
           @param uo A UO instance for msg output."""
        self._uo = uo
        self._interval_seconds = interval_seconds
        # Try to ensure we update the NTP time soon after (~ 1 second) after the WiFi is connected.
        self._next_update_seconds = utime.time() + 1
        # Set the NTP server to use.
        ntptime.host = NTP.NTP_HOST

    def handle(self):
        """@brief Called periodically in order to update the MCU time via NTP.
                  This may block for up to 1 second if the server is unreachable.
                  However as it's not called often we can live with this.
                  Generally this method executes (when an NTP sync is required)
                  in ~ 30 to 90 milli seconds although this is dependant upon
                  the internet connection RTT.
                  Tried executing this in a background _thread but this made the CT6
                  platform unstable.
            @param True if an NTP sync was performed and succeeded."""
        ntp_sync_success = False
        # If it's time to set the time via NTP
        if utime.time() >= self._next_update_seconds:
            ntp_sync_success = self._sync_time()
            self._next_update_seconds = utime.time() + self._interval_seconds
        return ntp_sync_success

    def _sync_time(self):
        """@brief Attempt to sync the system time usiong an NTP server.
                  This method may block for some time if the NTP server is not reachable.
           @return interval_seconds The number of seconds to elapse between each ntp sync attempt."""
        # We don't want to output to much data on the serial port here to ensure
        # we don't use to much time sending data over the serial port compared to the time
        # taken to update the NTP time.
        success = False
        start_t = utime.ticks_us()
        try:
            ntptime.settime()
            success = True
        except:
            pass
        elapsed_us = utime.ticks_us() - start_t
        if success:
            self._uo.info(f"NTP sync success. Took {elapsed_us} microseconds.")
        else:
            self._uo.error(f"NTP sync failure. Took {elapsed_us} microseconds.")
        return success

    def get_localtime(self):
        """@brief Get the local time on this MCU.
                  handle() must have been called and returned True for the correct time to be returned.
        """
        return utime.localtime()

    def get_local_time_string(self):
        """@brief Get a string of the local time. This is actually UTC time. Any local time GMT, BST etc
                  must be handled manually.
                  handle() must have been called and returned True for the correct time to be returned.
           @return A string in year-month-day hour:min:sec format.
        """
        t = self.get_localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2],   # year, month, day
                                                                  t[3], t[4], t[5]    # hour, minute, second
                                                                 )
