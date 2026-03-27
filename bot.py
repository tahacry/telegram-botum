def get_usd_try():
    try:
        rate = get_rate_from_main_source()
        if 10 < rate < 100:
            return rate
    except:
        pass

    try:
        rate = get_rate_from_backup_source()
        if 10 < rate < 100:
            return rate
    except:
        pass

    if last_good_rate is not None:
        return last_good_rate

    raise ValueError("Kur verisi alinamadi")
