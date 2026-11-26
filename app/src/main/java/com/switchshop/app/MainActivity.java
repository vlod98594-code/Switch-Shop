package com.switchshop.app;
import android.app.*;import android.os.*;import android.webkit.*;import android.widget.*;
public class MainActivity extends Activity {
public void onCreate(Bundle b){super.onCreate(b); WebView w=new WebView(this);setContentView(w);w.getSettings().setJavaScriptEnabled(true);w.getSettings().setDomStorageEnabled(true);w.setWebViewClient(new WebViewClient());w.loadUrl("file:///android_asset/index.html");}
}