    elif name == "tr_analyze_topic_trend":
        return _tools["analytics"].analyze_topic_trend_unified(
            topic=args.get("topic",""),
            analysis_type=args.get("analysis_type","trend"),
            date_range=args.get("date_range"),
            granularity=args.get("granularity","day"))
