package com.taskmaster.android;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.*;
import android.text.*;
import android.view.*;
import android.widget.*;
import com.taskmaster.android.model.TaskNode;
import com.taskmaster.android.util.TaskRepository;

import java.io.File;
import java.util.*;

public class MainActivity extends Activity {
    private static final int PERM_REQ = 1;
    private static final String PREFS  = "taskmaster";

    private ListView listView;
    private TextView emptyView;
    private TaskAdapter adapter;
    private List<TaskNode> rootTasks = new ArrayList<>();
    private List<TaskNode> flatTasks = new ArrayList<>();
    private String activeStatus = null;
    private boolean flagOnly    = false;
    private String searchQuery  = "";
    private File workspaceDir;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        setActionBar(toolbar);
        getActionBar().setTitle("Task Master");

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        emptyView = (TextView) findViewById(R.id.emptyView);
        listView  = (ListView) findViewById(R.id.taskList);

        adapter = new TaskAdapter(this, new TaskAdapter.OnToggleDone() {
            public void toggle(TaskNode task, int position) {
                task.status = task.isDone() ? "todo" : "done";
                TaskRepository.saveMeta(task);
                applyFilter();
            }
        });

        listView.setAdapter(adapter);
        listView.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            public void onItemClick(AdapterView<?> p, View v, int pos, long id) {
                openDetail(flatTasks.get(pos));
            }
        });

        buildFilterBar();

        EditText search = (EditText) findViewById(R.id.searchField);
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int st, int c, int a) {}
            public void afterTextChanged(Editable s) {}
            public void onTextChanged(CharSequence s, int st, int b, int c) {
                searchQuery = s.toString();
                applyFilter();
            }
        });

        Button newTaskBtn = (Button) findViewById(R.id.newTaskBtn);
        newTaskBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (workspaceDir == null) { toast("Workspace neni nastaven"); return; }
                Intent i = new Intent(MainActivity.this, EditTaskActivity.class);
                i.putExtra("parentPath", workspaceDir.getAbsolutePath());
                i.putExtra("isNew", true);
                startActivity(i);
            }
        });

        Button workspaceBtn = (Button) findViewById(R.id.workspaceBtn);
        workspaceBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { chooseWorkspace(); }
        });

        checkPermissions();
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadWorkspace();
    }

    private void checkPermissions() {
        if (checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED) {
            loadWorkspace();
        } else {
            requestPermissions(
                new String[]{Manifest.permission.READ_EXTERNAL_STORAGE,
                             Manifest.permission.WRITE_EXTERNAL_STORAGE},
                PERM_REQ);
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] grants) {
        if (code == PERM_REQ && grants.length > 0
                && grants[0] == PackageManager.PERMISSION_GRANTED)
            loadWorkspace();
        else
            toast("Potrebujeme pristup k ulozisti");
    }

    private void loadWorkspace() {
        String def  = Environment.getExternalStorageDirectory() + "/TaskMaster/workspace";
        String path = prefs.getString("workspace_path", def);
        workspaceDir = new File(path);
        if (!workspaceDir.exists()) workspaceDir.mkdirs();

        emptyView.setText("Nacitam...");
        emptyView.setVisibility(View.VISIBLE);
        listView.setVisibility(View.GONE);

        final File dir       = workspaceDir;
        final String fPath   = path;

        new Thread(new Runnable() {
            public void run() {
                final List<TaskNode> tasks = TaskRepository.loadWorkspace(dir);
                runOnUiThread(new Runnable() {
                    public void run() {
                        rootTasks = tasks;
                        applyFilter();
                        if (tasks.isEmpty()) {
                            emptyView.setText("Zadne ukoly\nWorkspace: " + fPath
                                + "\n\nVytvorte prvni ukol tlacitkem nize\nnebo nastavte jiny workspace.");
                            emptyView.setVisibility(View.VISIBLE);
                            listView.setVisibility(View.GONE);
                        } else {
                            emptyView.setVisibility(View.GONE);
                            listView.setVisibility(View.VISIBLE);
                        }
                    }
                });
            }
        }).start();
    }

    private void buildFilterBar() {
        LinearLayout bar = (LinearLayout) findViewById(R.id.filterBar);
        final String[][] filters = {
            {"all",        "Vse"},
            {"todo",       "Todo"},
            {"in_progress","Probiha"},
            {"blocked",    "Blokovano"},
            {"done",       "Hotovo"},
            {"_flag",      "Oznacene"}
        };
        for (int i = 0; i < filters.length; i++) {
            final String key   = filters[i][0];
            final String label = filters[i][1];
            Button btn = new Button(this);
            btn.setText(label);
            btn.setTextSize(11f);
            int pad = dpToPx(10);
            btn.setPadding(pad, dpToPx(4), pad, dpToPx(4));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dpToPx(36));
            lp.setMargins(dpToPx(3), dpToPx(4), dpToPx(3), dpToPx(4));
            btn.setLayoutParams(lp);
            btn.setBackgroundColor(Color.parseColor("#E0E0E0"));
            btn.setTextColor(Color.parseColor("#424242"));
            btn.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    if ("_flag".equals(key))  { flagOnly = !flagOnly; activeStatus = null; }
                    else if ("all".equals(key)) { activeStatus = null; flagOnly = false; }
                    else                        { activeStatus = key;  flagOnly = false; }
                    applyFilter();
                }
            });
            bar.addView(btn);
        }
    }

    private void applyFilter() {
        flatTasks.clear();
        flattenWithFilter(rootTasks, flatTasks);
        adapter.setItems(flatTasks);
    }

    private void flattenWithFilter(List<TaskNode> tasks, List<TaskNode> out) {
        for (TaskNode t : tasks) {
            if (matches(t)) out.add(t);
            flattenWithFilter(t.children, out);
        }
    }

    private boolean matches(TaskNode t) {
        if (activeStatus != null && !activeStatus.equals(t.status)) return false;
        if (flagOnly && !t.flag) return false;
        if (!searchQuery.isEmpty()) {
            String q = searchQuery.toLowerCase(Locale.getDefault());
            if (!t.title.toLowerCase(Locale.getDefault()).contains(q)
                    && !t.category.toLowerCase(Locale.getDefault()).contains(q)) return false;
        }
        return true;
    }

    private void openDetail(TaskNode t) {
        Intent i = new Intent(this, TaskDetailActivity.class);
        i.putExtra("folderPath", t.folderPath);
        startActivity(i);
    }

    private void chooseWorkspace() {
        final EditText input = new EditText(this);
        input.setText(prefs.getString("workspace_path",
            Environment.getExternalStorageDirectory() + "/TaskMaster/workspace"));
        new AlertDialog.Builder(this)
            .setTitle("Cesta k workspace")
            .setMessage("Absolutni cesta ke slozce workspace:")
            .setView(input)
            .setPositiveButton("Nastavit", new DialogInterface.OnClickListener() {
                public void onClick(DialogInterface d, int w) {
                    String path = input.getText().toString().trim();
                    if (!path.isEmpty()) {
                        prefs.edit().putString("workspace_path", path).apply();
                        loadWorkspace();
                    }
                }
            })
            .setNegativeButton("Zrusit", null)
            .show();
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private int dpToPx(int dp) {
        return (int)(dp * getResources().getDisplayMetrics().density + 0.5f);
    }
}
