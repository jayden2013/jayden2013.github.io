/*
 * Cars & Collectibles — Java Invoice Generator (Swing UI, no external deps)
 * Compile-safe, escaping-fixed version.
 *
 * Build/run:
 *   javac InvoiceApp.java && java InvoiceApp
 * (Java 8+)
 */

import javax.swing.*;
import javax.swing.border.EmptyBorder;
import javax.swing.event.TableModelEvent;
import javax.swing.event.TableModelListener;
import javax.swing.table.DefaultTableModel;
import java.awt.*;
import java.awt.datatransfer.StringSelection;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDate;
import java.util.*;

public class InvoiceApp extends JFrame {
	// ---- Files for small persistence ----
	private static final Path OUTPUT_DIR = Paths.get("invoices");
	private static final Path COUNTER_FILE = Paths.get(".invoice_counter");
	private static final Path SETTINGS_FILE = Paths.get(".invoice_settings.properties");

	// ---- Business defaults ----
	private static final String BIZ_NAME = "Cars & Collectibles LLC";
	private static final String BIZ_EMAIL = "sales@carsandcollectibles.com";
	private static final String BIZ_PHONE = "2089187761"; // optional
	private static final String BIZ_WEBSITE = "https://carsandcollectibles.com";
	private static final String BIZ_ADDRESS = "Boise, Idaho";

	// ---- UI fields ----
	private final JTextField tfBizName = new JTextField(BIZ_NAME);
	private final JTextField tfBizEmail = new JTextField(BIZ_EMAIL);
	private final JTextField tfBizPhone = new JTextField(BIZ_PHONE);
	private final JTextField tfBizWebsite = new JTextField(BIZ_WEBSITE);
	private final JTextField tfBizAddress = new JTextField(BIZ_ADDRESS);
	private final JTextField tfLogoPath = new JTextField(30);

	private final JTextField tfCustName = new JTextField(20);
	private final JTextField tfCustEmail = new JTextField(20);
	private final JTextField tfCustPhone = new JTextField(20);
	private final JTextArea taCustAddress = new JTextArea(3, 20);

	private final JTextField tfInvPrefix = new JTextField("INV-", 6);
	private final JTextField tfInvNumber = new JTextField(8);
	private final JTextField tfDate = new JTextField(LocalDate.now().toString(), 10);
	private final JTextField tfDue = new JTextField(LocalDate.now().toString(), 10);
	private final JTextField tfPO = new JTextField(12);

	private final JTextField tfCurrency = new JTextField("$", 3);
	private final JSpinner spTax = new JSpinner(new SpinnerNumberModel(0.0, 0.0, 100.0, 0.1));
	private final JSpinner spDiscount = new JSpinner(new SpinnerNumberModel(0.0, 0.0, 1_000_000.0, 0.5));

	private final JTextField tfTerms = new JTextField("Due upon receipt");
	private final JTextField tfAccepted = new JTextField("Cash, Venmo, PayPal");
	private final JTextArea taInstructions = new JTextArea(3, 20);
	private final JTextArea taNotes = new JTextArea(3, 20);

	private final JLabel lbSubtotal = new JLabel("$0.00");
	private final JLabel lbTax = new JLabel("$0.00");
	private final JLabel lbTotal = new JLabel("$0.00");
	private final JLabel lbDiscountAmt = new JLabel();

	private final JTable table;
	private final DefaultTableModel model;

	// --- Preset prices (edit these as you like) ---
	private static final double PRICE_MINI_SESSION = 50.0;
	private static final double PRICE_STILL_SESSION = 100.0;
	private static final double PRICE_ROLLER_SESSION = 200.0;
	private static final double PRICE_FULL_FEATURE = 400.0;

	// Guard to prevent recursion from our own table writes
	private boolean isRecalc = false;

	// Document type
	private enum DocType {
		INVOICE, QUOTE
	}

	private DocType docType = DocType.INVOICE;

	public InvoiceApp() {
		super("Invoice Generator — Cars & Collectibles");
		setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
		setMinimumSize(new Dimension(1100, 720));
		setLocationByPlatform(true);

		// Items table
		model = new DefaultTableModel(new Object[] { "Description", "Qty", "Rate", "Amount" }, 0) {
			@Override
			public boolean isCellEditable(int row, int col) {
				return col != 3;
			}

			@Override
			public Class<?> getColumnClass(int columnIndex) {
				if (columnIndex == 1 || columnIndex == 2 || columnIndex == 3)
					return Double.class;
				else
					return String.class;
			}
		};
		table = new JTable(model);
		table.putClientProperty("terminateEditOnFocusLost", Boolean.TRUE);
		table.setRowHeight(24);
		table.getColumnModel().getColumn(0).setPreferredWidth(480);
		table.getColumnModel().getColumn(1).setPreferredWidth(60);
		table.getColumnModel().getColumn(2).setPreferredWidth(80);
		table.getColumnModel().getColumn(3).setPreferredWidth(90);

		// Start with one blank row
		addBlankRow();

		model.addTableModelListener(new TableModelListener() {
			@Override
			public void tableChanged(TableModelEvent e) {
				if (isRecalc)
					return; // ignore our own updates
				int type = e.getType();
				if (type == TableModelEvent.UPDATE || type == TableModelEvent.INSERT
						|| type == TableModelEvent.DELETE) {
					int col = e.getColumn();
					if (col == 3)
						return; // ignore Amount column updates
					recalcTotals();
				}
			}
		});

		// Layout
		setContentPane(buildRoot());
		setJMenuBar(buildMenu());

		// Load settings & set next invoice number
		loadSettings();
		tfInvNumber.setText(nextInvoiceNumber(tfInvPrefix.getText().trim()));
		recalcTotals();
	}

	// Adds a new line if not found; otherwise bumps qty on the existing line.
	// If an existing line has rate == 0, we set it to the provided rate.
	private void addOrBumpItem(String description, double qtyToAdd, double rate) {
		int row = findRowByDescription(description);
		if (row >= 0) {
			double oldQty = toDouble(model.getValueAt(row, 1));
			model.setValueAt(oldQty + qtyToAdd, row, 1);
			double oldRate = toDouble(model.getValueAt(row, 2));
			if (Math.abs(oldRate) < 1e-9) {
				model.setValueAt(rate, row, 2);
			}
			recalcTotals();
			// optional: select the updated row
			table.getSelectionModel().setSelectionInterval(row, row);
		} else {
			model.addRow(new Object[] { description, qtyToAdd, rate, 0.0 });
			recalcTotals();
			int last = model.getRowCount() - 1;
			table.getSelectionModel().setSelectionInterval(last, last);
		}
	}

	// Finds a row whose Description matches (case-insensitive, trimmed)
	private int findRowByDescription(String description) {
		String target = normalizeDesc(description);
		for (int i = 0; i < model.getRowCount(); i++) {
			Object val = model.getValueAt(i, 0);
			if (val != null && normalizeDesc(val.toString()).equals(target)) {
				return i;
			}
		}
		return -1;
	}

	private static String normalizeDesc(String s) {
		return s == null ? "" : s.trim().replaceAll("\\s+", " ").toLowerCase(Locale.ROOT);
	}

	private JPanel buildRoot() {
		JPanel root = new JPanel(new BorderLayout());
		root.setBorder(new EmptyBorder(10, 10, 10, 10));

		JSplitPane split = new JSplitPane(JSplitPane.VERTICAL_SPLIT, buildTop(), buildBottom());
		split.setResizeWeight(0.6);
		root.add(split, BorderLayout.CENTER);
		root.add(buildBottomBar(), BorderLayout.SOUTH);
		return root;
	}

	private JComponent buildTop() {
		JPanel p = new JPanel(new GridBagLayout());
		GridBagConstraints c = new GridBagConstraints();
		c.insets = new Insets(4, 4, 4, 4);
		c.fill = GridBagConstraints.HORIZONTAL;
		c.weightx = 1;

		int y = 0;
		c.gridx = 0;
		c.gridy = y;
		p.add(sectionLabel("Business"), c);
		c.gridy = ++y;
		p.add(row(panel(label("Name"), tfBizName, label("Email"), tfBizEmail, label("Phone"), tfBizPhone)), c);
		c.gridy = ++y;
		p.add(row(panel(label("Website"), tfBizWebsite, label("Address"), tfBizAddress)), c);
		c.gridy = ++y;
		p.add(row(panel(label("Logo path"), tfLogoPath, browseButton(tfLogoPath))), c);

		c.gridy = ++y;
		p.add(sectionLabel("Bill To"), c);
		c.gridy = ++y;
		p.add(row(panel(label("Name"), tfCustName, label("Email"), tfCustEmail, label("Phone"), tfCustPhone)), c);
		c.gridy = ++y;
		p.add(row(panel(label("Address"), new JScrollPane(taCustAddress))), c);

		c.gridy = ++y;
		p.add(sectionLabel("Invoice"), c);
		c.gridy = ++y;
		p.add(row(panel(label("Prefix"), tfInvPrefix, label("Number"), tfInvNumber, label("Date"), tfDate, label("Due"),
				tfDue, label("PO #"), tfPO)), c);

		c.gridy = ++y;
		p.add(sectionLabel("Payment & Notes"), c);
		c.gridy = ++y;
		p.add(row(panel(label("Terms"), tfTerms, label("Accepted"), tfAccepted)), c);
		c.gridy = ++y;
		p.add(row(panel(label("Instructions"), new JScrollPane(taInstructions))), c);
		c.gridy = ++y;
		p.add(row(panel(label("Notes"), new JScrollPane(taNotes))), c);

		return new JScrollPane(p);
	}

	private JComponent buildBottom() {
		JPanel p = new JPanel(new BorderLayout());
		p.setBorder(new EmptyBorder(6, 0, 0, 0));

		JPanel bar = new JPanel(new FlowLayout(FlowLayout.LEFT));
		JButton btnAdd = new JButton("Add row");
		JButton btnRemove = new JButton("Remove row");
		JButton btnDuplicate = new JButton("Duplicate row");
		JButton btnPasteRows = new JButton("Paste rows");

		JButton btnMini = new JButton("Mini Session");
		btnMini.addActionListener(e -> addOrBumpItem("Mini Session", 1, PRICE_MINI_SESSION));

		JButton btnStill = new JButton("Still Session");
		btnStill.addActionListener(e -> addOrBumpItem("Still Session", 1, PRICE_STILL_SESSION));

		JButton btnRoller = new JButton("Roller Session");
		btnRoller.addActionListener(e -> addOrBumpItem("Roller Session", 1, PRICE_ROLLER_SESSION));

		JButton btnFeature = new JButton("Full Feature");
		btnFeature.addActionListener(e -> addOrBumpItem("Full Feature", 1, PRICE_FULL_FEATURE));

		btnAdd.addActionListener(e -> addBlankRow());
		btnRemove.addActionListener(e -> removeSelectedRow());
		btnDuplicate.addActionListener(e -> duplicateSelectedRow());
		btnPasteRows.addActionListener(e -> pasteRowsFromClipboard());

		bar.add(btnAdd);
		bar.add(btnRemove);
		bar.add(btnDuplicate);
		bar.add(btnPasteRows);
		bar.add(btnMini);
		bar.add(btnStill);
		bar.add(btnRoller);
		bar.add(btnFeature);

		p.add(bar, BorderLayout.NORTH);
		p.add(new JScrollPane(table), BorderLayout.CENTER);
		return p;
	}

	private JComponent buildBottomBar() {
		JPanel p = new JPanel(new BorderLayout());

		JPanel totals = new JPanel(new GridLayout(1, 6, 12, 0));
		totals.add(right(label("Subtotal:")));
		totals.add(right(lbSubtotal));
		totals.add(right(label("Tax:")));
		totals.add(right(lbTax));
		totals.add(right(label("Discount:")));
		totals.add(right(lbDiscountAmt));
		totals.add(right(bold("Total:")));
		totals.add(right(bold(lbTotal)));

		JComboBox<String> cbDocType = new JComboBox<>(new String[] { "Invoice", "Quote" });
		cbDocType.setSelectedIndex(docType == DocType.QUOTE ? 1 : 0);
		cbDocType.addActionListener(e -> {
			docType = (cbDocType.getSelectedIndex() == 1) ? DocType.QUOTE : DocType.INVOICE;
			// Optional: nudge prefix if it looks default-y
			String pfx = tfInvPrefix.getText().trim();
			if (pfx.isEmpty() || pfx.equals("INV-") || pfx.equals("Q-")) {
				tfInvPrefix.setText(docType == DocType.QUOTE ? "Q-" : "INV-");
			}
			
			if (pfx.equals("INV-")) {
				int i = tfInvNumber.getText().indexOf("-");
				tfInvNumber.setText("Q-" + tfInvNumber.getText().substring(i+1));
			} else {
				int i = tfInvNumber.getText().indexOf("-");
				tfInvNumber.setText("INV-" + tfInvNumber.getText().substring(i+1));
			}
			
			// Update window title
			setTitle((docType == DocType.QUOTE ? "Quote" : "Invoice") + " Generator — Cars & Collectibles");
		});

		JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
		actions.add(new JLabel("Doc Type:"));
		actions.add(cbDocType);
		JButton btnNextNo = new JButton("Next #");
		JButton btnDiscount = new JButton("Discount…");
		JButton btnToggleTax = new JButton("Toggle Tax");
		btnToggleTax.addActionListener(e -> toggleTax());
		JButton btnExport = new JButton("Export HTML");
		JButton btnOpen = new JButton("Open in Browser");

		btnNextNo.addActionListener(e -> {
			String prefix = tfInvPrefix.getText().trim();
			if (prefix.isEmpty())
				prefix = (docType == DocType.QUOTE ? "Q-" : "INV-");
			tfInvNumber.setText(nextInvoiceNumber(prefix));
		});

		btnDiscount.addActionListener(e -> {
			JPopupMenu menu = makeDiscountMenu();
			menu.show(btnDiscount, 0, btnDiscount.getHeight());
		});
		btnExport.addActionListener(e -> exportHtml(false));
		btnOpen.addActionListener(e -> exportHtml(true));

		actions.add(btnNextNo);
		actions.add(btnToggleTax);
		actions.add(btnDiscount);
		actions.add(btnExport);
		actions.add(btnOpen);

		p.add(totals, BorderLayout.WEST);
		p.add(actions, BorderLayout.EAST);
		return p;
	}

	private void addItem(String description, double qty, double rate) {
		model.addRow(new Object[] { description, qty, rate, 0.0 });
		recalcTotals();
	}

	private JMenuBar buildMenu() {
		JMenuBar mb = new JMenuBar();
		JMenu file = new JMenu("File");
		JMenuItem miSaveDraft = new JMenuItem("Save Draft (.json)");
		JMenuItem miLoadDraft = new JMenuItem("Load Draft (.json)");
		JMenuItem miQuit = new JMenuItem("Quit");
		miSaveDraft.addActionListener(e -> saveDraft());
		miLoadDraft.addActionListener(e -> loadDraft());
		miQuit.addActionListener(e -> System.exit(0));
		file.add(miSaveDraft);
		file.add(miLoadDraft);
		file.addSeparator();
		file.add(miQuit);

		JMenu edit = new JMenu("Edit");
		JMenuItem miCopyTotal = new JMenuItem("Copy Total to Clipboard");
		miCopyTotal.addActionListener(e -> copyToClipboard(lbTotal.getText()));
		edit.add(miCopyTotal);

		JMenu help = new JMenu("Help");
		JMenuItem miAbout = new JMenuItem("About");
		miAbout.addActionListener(e -> JOptionPane.showMessageDialog(this, "Cars & Collectibles Invoice Generator",
				"About", JOptionPane.INFORMATION_MESSAGE));
		help.add(miAbout);

		mb.add(file);
		mb.add(edit);
		mb.add(help);
		return mb;
	}

	// ---- Table helpers ----
	private void addBlankRow() {
		model.addRow(new Object[] { "", 1.0, 0.0, 0.0 });
	}

	private void removeSelectedRow() {
		int i = table.getSelectedRow();
		if (i >= 0)
			model.removeRow(i);
		recalcTotals();
	}

	private void duplicateSelectedRow() {
		int i = table.getSelectedRow();
		if (i >= 0) {
			Object d = model.getValueAt(i, 0);
			Object q = model.getValueAt(i, 1);
			Object r = model.getValueAt(i, 2);
			model.addRow(new Object[] { d, q, r, 0.0 });
		}
		recalcTotals();
	}

	private void pasteRowsFromClipboard() {
		try {
			String s = (String) Toolkit.getDefaultToolkit().getSystemClipboard()
					.getData(java.awt.datatransfer.DataFlavor.stringFlavor);
			if (s == null || s.trim().isEmpty())
				return;
			String[] lines = s.split("\\r?\\n");
			for (String line : lines) {
				String[] parts = line.split("\\t|,");
				if (parts.length >= 3) {
					String desc = parts[0].trim();
					double qty = parseDoubleSafe(parts[1]);
					double rate = parseDoubleSafe(parts[2]);
					model.addRow(new Object[] { desc, qty, rate, 0.0 });
				}
			}
			recalcTotals();
		} catch (Exception ignored) {
		}
	}

	// ---- Calculations ----
	private void recalcTotals() {
		if (isRecalc)
			return;
		isRecalc = true;
		try {
			double subtotal = 0.0;
			for (int i = 0; i < model.getRowCount(); i++) {
				double qty = toDouble(model.getValueAt(i, 1));
				double rate = toDouble(model.getValueAt(i, 2));
				double amt = round2(qty * rate);
				Object old = model.getValueAt(i, 3);
				double oldVal = (old instanceof Number) ? ((Number) old).doubleValue() : toDouble(old);
				if (Math.abs(oldVal - amt) > 0.0001) {
					model.setValueAt(amt, i, 3); // guarded by isRecalc
				}
				subtotal += amt;
			}
			double taxRate = ((Number) spTax.getValue()).doubleValue();
			double discount = ((Number) spDiscount.getValue()).doubleValue();
			double tax = round2(subtotal * (taxRate / 100.0));
			double total = Math.max(0.0, round2(subtotal + tax - discount));

			String cur = tfCurrency.getText().trim();
			if (cur.isEmpty())
				cur = "$";
			lbSubtotal.setText(money(subtotal, cur));
			lbTax.setText(money(tax, cur));
			lbDiscountAmt.setText("-" + money(discount, cur));
			lbTotal.setText(money(total, cur));
		} finally {
			isRecalc = false;
		}
	}

	private static double toDouble(Object o) {
		if (o == null)
			return 0.0;
		if (o instanceof Number)
			return ((Number) o).doubleValue();
		try {
			return Double.parseDouble(o.toString());
		} catch (Exception e) {
			return 0.0;
		}
	}

	private static double parseDoubleSafe(String s) {
		try {
			return Double.parseDouble(s.trim());
		} catch (Exception e) {
			return 0.0;
		}
	}

	private static double round2(double v) {
		return Math.round(v * 100.0) / 100.0;
	}

	private static String money(double v, String cur) {
		return cur + String.format(Locale.US, "%,.2f", v);
	}

	// ---- Export HTML ----
	private void exportHtml(boolean openAfter) {
		try {
			ensureDirs();
			String invNo = tfInvNumber.getText().trim();
			if (invNo.isEmpty()) {
				JOptionPane.showMessageDialog(this, "Invoice number is empty", "Error", JOptionPane.ERROR_MESSAGE);
				return;
			}
			String fileSafe = invNo.replace('/', '-');
			Path out = OUTPUT_DIR.resolve(fileSafe + ".html");
			String html = renderHtml();
			Files.write(out, html.getBytes(StandardCharsets.UTF_8));
			saveSettings();
			JOptionPane.showMessageDialog(this, "Saved:\n" + out.toAbsolutePath());
			if (openAfter && Desktop.isDesktopSupported()) {
				Desktop.getDesktop().browse(out.toUri());
			}
		} catch (Exception ex) {
			ex.printStackTrace();
			JOptionPane.showMessageDialog(this, "Failed to export HTML: " + ex.getMessage(), "Error",
					JOptionPane.ERROR_MESSAGE);
		}
	}

	private String renderHtml() throws IOException {
		String css = BASE_CSS.replace("__PAGE_SIZE__", "letter"); // change to "a4" if desired
		String logoImg = base64LogoImg(tfLogoPath.getText().trim());

		String cur = tfCurrency.getText().trim();
		if (cur.isEmpty())
			cur = "$";
		
		String docTitle = (docType == DocType.QUOTE) ? "Quote" : "Invoice";
		String docNumberLabel = (docType == DocType.QUOTE) ? "Quote #" : "Invoice #";
		String dueLabel = (docType == DocType.QUOTE) ? "Valid until" : "Due";


		StringBuilder rows = new StringBuilder();
		for (int i = 0; i < model.getRowCount(); i++) {
			String desc = escape(String.valueOf(model.getValueAt(i, 0)));
			double qty = toDouble(model.getValueAt(i, 1));
			double rate = toDouble(model.getValueAt(i, 2));
			double amt = toDouble(model.getValueAt(i, 3));
			rows.append("<tr>").append("<td>").append(desc).append("</td>").append("<td class='right'>")
					.append(trimZeros(qty)).append("</td>").append("<td class='right'>").append(money(rate, cur))
					.append("</td>").append("<td class='right'>").append(money(amt, cur)).append("</td></tr>\n");
		}

		double subtotal = unmoney(lbSubtotal.getText());
		double tax = unmoney(lbTax.getText());
		double total = unmoney(lbTotal.getText());

		return HTML_TEMPLATE.replace("{css}", css).replace("{logo_img}", logoImg)
				.replace("{business_name}", escape(tfBizName.getText()))
				.replace("{business_email}", escape(tfBizEmail.getText()))
				.replace("{business_phone}", safeDiv(tfBizPhone.getText()))
				.replace("{business_website}", escape(tfBizWebsite.getText()))
				.replace("{business_address}", safeDiv(tfBizAddress.getText()))
				.replace("{cust_name}", escape(tfCustName.getText()))
				.replace("{cust_email}", escape(tfCustEmail.getText()))
				.replace("{cust_phone}", escape(tfCustPhone.getText()))
				.replace("{cust_address}", escape(taCustAddress.getText()))
				.replace("{inv_number}", escape(tfInvNumber.getText())).replace("{inv_date}", escape(tfDate.getText()))
				.replace("{due_date}", escape(tfDue.getText())).replace("{po_number}", escape(tfPO.getText()))
				.replace("{terms}", escape(tfTerms.getText())).replace("{rows}", rows.toString())
				.replace("{subtotal}", escape(money(subtotal, cur)))
				.replace("{tax_rate}", String.format(Locale.US, "%.2f", ((Number) spTax.getValue()).doubleValue()))
				.replace("{tax}", escape(money(tax, cur)))
				.replace("{discount}", escape(money(((Number) spDiscount.getValue()).doubleValue(), cur)))
				.replace("{total}", escape(money(total, cur))).replace("{notes}", escape(taNotes.getText()))
				.replace("{accepted_methods}", escape(tfAccepted.getText()))
				.replace("{instructions}", escape(taInstructions.getText()))
        		.replace("{doc_title}", docTitle)
        		.replace("{doc_number_label}", docNumberLabel)
        		.replace("{due_label}", dueLabel);
	}

	private static String trimZeros(double d) {
		if (Math.abs(d - Math.rint(d)) < 1e-9)
			return String.valueOf((long) Math.rint(d));
		return String.format(Locale.US, "%s", d);
	}

	private static String safeDiv(String s) {
		s = (s == null) ? "" : s.trim();
		return s.isEmpty() ? "" : ("<div>" + escape(s) + "</div>");
	}

	private static double unmoney(String s) {
		if (s == null)
			return 0.0;
		return toDouble(s.replaceAll("[^0-9.-]", ""));
	}

	private static String base64LogoImg(String path) throws IOException {
		if (path == null || path.isEmpty())
			return "";
		Path p = Paths.get(path);
		if (!Files.exists(p))
			return "";
		byte[] data = Files.readAllBytes(p);
		String b64 = Base64.getEncoder().encodeToString(data);
		String ext = extLower(p.getFileName().toString());
		return "<img class=\"logo\" src=\"data:image/" + ext + ";base64," + b64 + "\" alt=\"logo\"/>";
	}

	private static String extLower(String name) {
		int i = name.lastIndexOf('.') + 1;
		return i > 0 && i < name.length() ? name.substring(i).toLowerCase(Locale.ROOT) : "png";
	}

	private static void ensureDirs() throws IOException {
		Files.createDirectories(OUTPUT_DIR);
	}

	// ---- Counter & settings ----
	private static String nextInvoiceNumber(String prefix) {
		int n = readCounter() + 1;
		writeCounter(n);
		if (prefix == null || prefix.isEmpty())
			prefix = "INV-";
		return prefix + String.format(Locale.US, "%04d", n);
	}

	private static int readCounter() {
		try {
			if (Files.exists(COUNTER_FILE)) {
				String t = new String(Files.readAllBytes(COUNTER_FILE), StandardCharsets.UTF_8).trim();
				return Integer.parseInt(t);
			}
		} catch (Exception ignored) {
		}
		return 0;
	}

	private static void writeCounter(int n) {
		try {
			Files.write(COUNTER_FILE, String.valueOf(n).getBytes(StandardCharsets.UTF_8));
		} catch (Exception ignored) {
		}
	}

	private void saveSettings() {
		Properties p = new Properties();
		p.setProperty("last.logo", tfLogoPath.getText());
		p.setProperty("last.dir", OUTPUT_DIR.toAbsolutePath().toString());
		p.setProperty("prefix", tfInvPrefix.getText());
		try (OutputStream os = Files.newOutputStream(SETTINGS_FILE)) {
			p.store(os, "invoice settings");
		} catch (Exception ignored) {
		}
	}

	private void loadSettings() {
		if (!Files.exists(SETTINGS_FILE))
			return;
		Properties p = new Properties();
		try (InputStream is = Files.newInputStream(SETTINGS_FILE)) {
			p.load(is);
		} catch (Exception ignored) {
		}
		tfLogoPath.setText(p.getProperty("last.logo", ""));
		tfInvPrefix.setText(p.getProperty("prefix", "INV-"));
	}

	// ---- Draft save/load ----
	private void saveDraft() {
		JFileChooser fc = new JFileChooser();
		fc.setDialogTitle("Save Draft (.json)");
		fc.setSelectedFile(new File("invoice_draft.json"));
		if (fc.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
			File f = fc.getSelectedFile();
			try {
				Files.writeString(f.toPath(), toJson(), StandardCharsets.UTF_8);
			} catch (Exception ex) {
				JOptionPane.showMessageDialog(this, "Failed: " + ex.getMessage());
			}
		}
	}

	private void loadDraft() {
		JFileChooser fc = new JFileChooser();
		fc.setDialogTitle("Load Draft (.json)");
		if (fc.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
			File f = fc.getSelectedFile();
			try {
				fromJson(Files.readString(f.toPath(), StandardCharsets.UTF_8));
				recalcTotals();
			} catch (Exception ex) {
				JOptionPane.showMessageDialog(this, "Failed: " + ex.getMessage());
			}
		}
	}

	private String toJson() {
		StringBuilder sb = new StringBuilder();
		sb.append("{\n");
		// Business
		kv(sb, "biz_name", tfBizName.getText(), true);
		kv(sb, "biz_email", tfBizEmail.getText(), true);
		kv(sb, "biz_phone", tfBizPhone.getText(), true);
		kv(sb, "biz_website", tfBizWebsite.getText(), true);
		kv(sb, "biz_address", tfBizAddress.getText(), true);
		kv(sb, "logo_path", tfLogoPath.getText(), true);
		// Customer
		kv(sb, "cust_name", tfCustName.getText(), true);
		kv(sb, "cust_email", tfCustEmail.getText(), true);
		kv(sb, "cust_phone", tfCustPhone.getText(), true);
		kv(sb, "cust_address", taCustAddress.getText(), true);
		// Invoice
		kv(sb, "inv_prefix", tfInvPrefix.getText(), true);
		kv(sb, "inv_number", tfInvNumber.getText(), true);
		kv(sb, "inv_date", tfDate.getText(), true);
		kv(sb, "inv_due", tfDue.getText(), true);
		kv(sb, "po_number", tfPO.getText(), true);
		// Pricing
		kv(sb, "currency", tfCurrency.getText(), true);
		kv(sb, "tax_percent", ((Number) spTax.getValue()).toString(), true);
		kv(sb, "discount", ((Number) spDiscount.getValue()).toString(), true);
		// Payment/notes
		kv(sb, "terms", tfTerms.getText(), true);
		kv(sb, "accepted", tfAccepted.getText(), true);
		kv(sb, "instructions", taInstructions.getText(), true);
		kv(sb, "notes", taNotes.getText(), true);
		kv(sb, "doc_type", (docType == DocType.QUOTE ? "quote" : "invoice"), true);
		// Items array
		sb.append("  \"items\": [\n");
		for (int i = 0; i < model.getRowCount(); i++) {
			if (i > 0)
				sb.append(",\n");
			sb.append("    {");
			sb.append("\"description\": \"").append(escJson(String.valueOf(model.getValueAt(i, 0)))).append("\",");
			sb.append(" \"qty\": ").append(toDouble(model.getValueAt(i, 1)));
			sb.append(", \"rate\": ").append(toDouble(model.getValueAt(i, 2)));
			sb.append(" }");
		}
		sb.append("\n  ]\n");
		sb.append("}\n");
		return sb.toString();
	}

	private void fromJson(String json) {
		// Minimal parser for our schema
		Map<String, String> map = new HashMap<>();
		for (String line : json.split("\\r?\\n")) {
			String s = line.trim();
			if (!s.startsWith("\""))
				continue;
			int kEnd = s.indexOf('"', 1);
			if (kEnd <= 1)
				continue;
			String key = s.substring(1, kEnd);
			int colon = s.indexOf(':', kEnd);
			if (colon < 0)
				continue;
			String val = s.substring(colon + 1).trim();
			if (val.endsWith(","))
				val = val.substring(0, val.length() - 1).trim();
			if (val.startsWith("\"")) {
				int vEnd = val.lastIndexOf('"');
				if (vEnd > 0)
					val = val.substring(1, vEnd);
				val = unescJson(val);
			}
			map.put(key, val);
		}
		tfBizName.setText(map.getOrDefault("biz_name", BIZ_NAME));
		tfBizEmail.setText(map.getOrDefault("biz_email", BIZ_EMAIL));
		tfBizPhone.setText(map.getOrDefault("biz_phone", BIZ_PHONE));
		tfBizWebsite.setText(map.getOrDefault("biz_website", BIZ_WEBSITE));
		tfBizAddress.setText(map.getOrDefault("biz_address", BIZ_ADDRESS));
		tfLogoPath.setText(map.getOrDefault("logo_path", ""));

		tfCustName.setText(map.getOrDefault("cust_name", ""));
		tfCustEmail.setText(map.getOrDefault("cust_email", ""));
		tfCustPhone.setText(map.getOrDefault("cust_phone", ""));
		taCustAddress.setText(map.getOrDefault("cust_address", ""));

		tfInvPrefix.setText(map.getOrDefault("inv_prefix", "INV-"));
		tfInvNumber.setText(map.getOrDefault("inv_number", nextInvoiceNumber(tfInvPrefix.getText())));
		tfDate.setText(map.getOrDefault("inv_date", LocalDate.now().toString()));
		tfDue.setText(map.getOrDefault("inv_due", LocalDate.now().toString()));
		tfPO.setText(map.getOrDefault("po_number", ""));

		tfCurrency.setText(map.getOrDefault("currency", "$"));
		try {
			spTax.setValue(Double.parseDouble(map.getOrDefault("tax_percent", "6.0")));
		} catch (Exception ignored) {
		}
		try {
			spDiscount.setValue(Double.parseDouble(map.getOrDefault("discount", "0.0")));
		} catch (Exception ignored) {
		}

		tfTerms.setText(map.getOrDefault("terms", "Due upon receipt"));
		tfAccepted.setText(map.getOrDefault("accepted", "Cash, Card"));
		taInstructions.setText(map.getOrDefault("instructions", ""));
		taNotes.setText(map.getOrDefault("notes", ""));
		
		String t = map.getOrDefault("doc_type", "invoice").toLowerCase(Locale.ROOT);
		docType = "quote".equals(t) ? DocType.QUOTE : DocType.INVOICE;
		setTitle((docType == DocType.QUOTE ? "Quote" : "Invoice") + " Generator — Cars & Collectibles");
		// Also reflect in prefix if it's default-y
		String pfx = tfInvPrefix.getText().trim();
		if (pfx.isEmpty() || pfx.equals("INV-") || pfx.equals("Q-")) {
		    tfInvPrefix.setText(docType == DocType.QUOTE ? "Q-" : "INV-");
		}


		// Items
		model.setRowCount(0);
		String itemsBlock = extractArray(json, "items");
		if (itemsBlock != null) {
			String[] objs = itemsBlock.split("\\},");
			for (String obj : objs) {
				String desc = extractJsonString(obj, "description");
				double qty = parseDoubleSafe(extractJsonNumber(obj, "qty"));
				double rate = parseDoubleSafe(extractJsonNumber(obj, "rate"));
				model.addRow(new Object[] { desc == null ? "" : desc, qty, rate, 0.0 });
			}
		}
	}

	private static String extractArray(String json, String key) {
		int i = json.indexOf("\"" + key + "\"");
		if (i < 0)
			return null;
		int s = json.indexOf('[', i);
		if (s < 0)
			return null;
		int depth = 0;
		for (int p = s; p < json.length(); p++) {
			char ch = json.charAt(p);
			if (ch == '[')
				depth++;
			else if (ch == ']') {
				depth--;
				if (depth == 0)
					return json.substring(s + 1, p);
			}
		}
		return null;
	}

	private static String extractJsonString(String src, String key) {
		String pat = "\"" + key + "\"";
		int i = src.indexOf(pat);
		if (i < 0)
			return null;
		int q1 = src.indexOf('"', i + pat.length());
		int q2 = src.indexOf('"', q1 + 1);
		if (q1 < 0 || q2 < 0)
			return null;
		return unescJson(src.substring(q1 + 1, q2));
	}

	private static String extractJsonNumber(String src, String key) {
		String pat = "\"" + key + "\"";
		int i = src.indexOf(pat);
		if (i < 0)
			return "0";
		int colon = src.indexOf(':', i + pat.length());
		if (colon < 0)
			return "0";
		int end = colon + 1;
		while (end < src.length() && " 0123456789.-".indexOf(src.charAt(end)) >= 0)
			end++;
		return src.substring(colon + 1, end).trim();
	}

	private static void kv(StringBuilder sb, String k, String v, boolean comma) {
		sb.append("  \"").append(escJson(k)).append("\": \"").append(escJson(v == null ? "" : v)).append("\"");
		sb.append(comma ? ",\n" : "\n");
	}

	private static String escJson(String s) {
		return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
	}

	private static String unescJson(String s) {
		return s.replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\");
	}

	// ---- HTML template & CSS ----
	private static final String BASE_CSS = ("@media print {" + "  @page { size: __PAGE_SIZE__; margin: 0.6in; }" + "}"
			+ ":root { --text:#111; --muted:#666; --line:#e5e7eb; --brand:#111827;}" + "*{box-sizing:border-box}"
			+ "body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,Noto Sans,sans-serif;margin:0;color:var(--text)}"
			+ ".wrapper{max-width:8.5in;margin:0 auto;padding:32px}"
			+ ".header{display:flex;justify-content:space-between;align-items:center;gap:16px}"
			+ ".brand{display:flex;align-items:center;gap:12px}"
			+ ".brand .name{font-size:20px;font-weight:700;color:var(--brand)}"
			+ ".brand .meta{font-size:12px;color:var(--muted)}"
			+ ".logo{width:56px;height:56px;object-fit:contain;border-radius:8px;border:1px solid var(--line);padding:6px;background:#fff}"
			+ ".h1{font-size:28px;font-weight:800}"
			+ ".grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}"
			+ ".card{border:1px solid var(--line);border-radius:12px;padding:14px}"
			+ ".small{font-size:12px;color:var(--muted)}"
			+ ".kv{display:grid;grid-template-columns:120px 1fr;gap:8px;font-size:13px}"
			+ ".table{width:100%;border-collapse:collapse;margin-top:16px}"
			+ ".table th,.table td{border-bottom:1px solid var(--line);padding:10px 8px;font-size:13px;vertical-align:top}"
			+ ".table th{text-align:left;font-weight:700;background:#fafafa}" + ".right{text-align:right}"
			+ ".totals{margin-top:10px;margin-left:auto;width:320px}"
			+ ".totals .row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line);font-size:14px}"
			+ ".totals .total{font-weight:800;font-size:18px;border-bottom:none;padding-top:10px}"
			+ ".footer{display:flex;gap:16px;margin-top:18px}"
			+ ".note,.pay{flex:1;border:1px solid var(--line);border-radius:12px;padding:12px}"
			+ ".badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#111;color:#fff;font-size:11px;font-weight:700;letter-spacing:.3px}"
			+ ".mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,\"Liberation Mono\",\"Courier New\",monospace;}");

	private static final String HTML_TEMPLATE = ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
			+ "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
			+ "<title>{inv_number} — {doc_title} — {business_name}</title>" + "<style>{css}</style></head><body>"
			+ "<div class=\"wrapper\">" + "  <div class=\"header\">"
			+ "    <div class=\"brand\">{logo_img}<div><div class=\"name\">{business_name}</div>"
			+ "      <div class=\"meta\">{business_address}{business_phone}<div><a href=\"mailto:{business_email}\">{business_email}</a> · <a href=\"{business_website}\">{business_website}</a></div></div>"
			+ "    </div></div><div class=\"h1\">{doc_title}</div></div>" + "  <div class=\"grid\">"
			+ "    <div class=\"card\"><div class=\"small\">BILL TO</div><div style=\"margin-top:6px;font-weight:700\">{cust_name}</div>"
			+ "      <div>{cust_address}</div><div>{cust_phone}</div><div><a href=\"mailto:{cust_email}\">{cust_email}</a></div></div>"
			+ "    <div class=\"card\"><div class=\"kv\"><div>{doc_number_label}</div><div class=\"mono\">{inv_number}</div><div>Date</div><div>{inv_date}</div>"
			+ "      <div>{due_label}</div><div>{due_date}</div><div>PO #</div><div>{po_number}</div><div>Terms</div><div>{terms}</div></div></div>"
			+ "  </div>"
			+ "  <table class=\"table\"><thead><tr><th style=\"width:60%\">Description</th><th class=\"right\">Qty</th><th class=\"right\">Rate</th><th class=\"right\">Amount</th></tr></thead><tbody>{rows}</tbody></table>"
			+ "  <div class=\"totals\"><div class=\"row\"><span>Subtotal</span><span>{subtotal}</span></div>"
			+ "    <div class=\"row\"><span>Tax ({tax_rate}%)</span><span>{tax}</span></div>"
			+ "    <div class=\"row\"><span>Discount</span><span>-{discount}</span></div>"
			+ "    <div class=\"row total\"><span>Total</span><span>{total}</span></div></div>"
			+ "  <div class=\"footer\"><div class=\"note\"><div class=\"small\" style=\"margin-bottom:6px\">NOTES</div><div>{notes}</div></div>"
			+ "    <div class=\"pay\"><div class=\"small\" style=\"margin-bottom:6px\">PAYMENT</div><div><span class=\"badge\">Accepted</span> {accepted_methods}</div>"
			+ "    <pre class=\"mono\" style=\"white-space:pre-wrap;margin-top:8px\">{instructions}</pre></div></div>"
			+ "</div></body></html>");

	// ---- Small utilities ----
	private static JLabel label(String s) {
		return new JLabel(s);
	}

	private static JLabel bold(String s) {
		JLabel l = new JLabel(s);
		l.setFont(l.getFont().deriveFont(Font.BOLD));
		return l;
	}

	private static JLabel bold(JLabel l) {
		l.setFont(l.getFont().deriveFont(Font.BOLD));
		return l;
	}

	private static JPanel panel(Component... cs) {
		JPanel p = new JPanel(new FlowLayout(FlowLayout.LEFT, 8, 0));
		for (Component c : cs)
			p.add(c);
		return p;
	}

	private static JPanel row(Component c) {
		JPanel p = new JPanel(new BorderLayout());
		p.add(c, BorderLayout.CENTER);
		return p;
	}

	private static Component right(Component c) {
		JPanel p = new JPanel(new FlowLayout(FlowLayout.RIGHT));
		p.add(c);
		return p;
	}

	private JButton browseButton(JTextField target) {
		JButton b = new JButton("Browse…");
		b.addActionListener(e -> {
			JFileChooser fc = new JFileChooser();
			if (fc.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
				target.setText(fc.getSelectedFile().getAbsolutePath());
			}
		});
		return b;
	}

	private static String escape(String s) {
		if (s == null)
			return "";
		return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'",
				"&#x27;");
	}

	private static void copyToClipboard(String s) {
		try {
			Toolkit.getDefaultToolkit().getSystemClipboard().setContents(new StringSelection(s), null);
		} catch (Exception ignored) {
		}
	}

	private static JComponent sectionLabel(String s) {
		JLabel l = new JLabel(s);
		l.setBorder(new EmptyBorder(8, 0, 0, 0));
		l.setFont(l.getFont().deriveFont(Font.BOLD, l.getFont().getSize2D() + 1f));
		return l;
	}

	// ---- Main ----
	public static void main(String[] args) {
		SwingUtilities.invokeLater(() -> {
			setSystemLookAndFeel();
			new InvoiceApp().setVisible(true);
		});
	}

	private static void setSystemLookAndFeel() {
		try {
			UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
		} catch (Exception ignored) {
		}
	}

	// ---- Discount helpers ----
	private JPopupMenu makeDiscountMenu() {
		JPopupMenu m = new JPopupMenu();

		JMenu percent = new JMenu("Percent off");
		double[] presets = { 5, 10, 15, 20 };
		for (double pct : presets) {
			JMenuItem it = new JMenuItem(String.format(Locale.US, "%.0f%%", pct));
			it.addActionListener(e -> applyPercentDiscount(pct));
			percent.add(it);
		}
		JMenuItem customPct = new JMenuItem("Custom % …");
		customPct.addActionListener(e -> {
			String s = JOptionPane.showInputDialog(this, "Percent off (e.g. 12.5)", "Custom Discount",
					JOptionPane.QUESTION_MESSAGE);
			if (s != null) {
				try {
					applyPercentDiscount(Double.parseDouble(s));
				} catch (Exception ignored) {
				}
			}
		});
		percent.addSeparator();
		percent.add(customPct);

		JMenuItem flat = new JMenuItem("Flat $ …");
		flat.addActionListener(e -> {
			String s = JOptionPane.showInputDialog(this, "Flat amount (e.g. 25)", "Flat Discount",
					JOptionPane.QUESTION_MESSAGE);
			if (s != null) {
				try {
					applyFlatDiscount(Double.parseDouble(s));
				} catch (Exception ignored) {
				}
			}
		});

		JMenuItem clear = new JMenuItem("Clear discount");
		clear.addActionListener(e -> {
			spDiscount.setValue(0.0);
			recalcTotals();
		});

		m.add(percent);
		m.add(flat);
		m.addSeparator();
		m.add(clear);
		return m;
	}

	private void applyPercentDiscount(double pct) {
		double subtotal = currentSubtotal();
		double amt = round2(subtotal * (pct / 100.0));
		spDiscount.setValue(amt);
		recalcTotals();
	}

	private void applyFlatDiscount(double amt) {
		if (amt < 0)
			amt = 0;
		spDiscount.setValue(round2(amt));
		recalcTotals();
	}

	private double currentSubtotal() {
		// Prefer the Amount column (already computed)
		double subtotal = 0.0;
		for (int i = 0; i < model.getRowCount(); i++) {
			subtotal += toDouble(model.getValueAt(i, 3));
		}
		// Fallback if amounts haven’t populated yet
		if (subtotal == 0.0) {
			for (int i = 0; i < model.getRowCount(); i++) {
				subtotal += round2(toDouble(model.getValueAt(i, 1)) * toDouble(model.getValueAt(i, 2)));
			}
		}
		return subtotal;
	}

	private void toggleTax() {
		double current = ((Number) spTax.getValue()).doubleValue();
		if (current > 0.0) {
			spTax.setValue(0.0);
		} else {
			spTax.setValue(6.0); // or your preferred default tax rate
		}
		recalcTotals();
	}

}
